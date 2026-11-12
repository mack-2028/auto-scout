"""
AUTO SCOUT  -  watches match videos on your laptop and writes down rough stats.

How to run (after the one-time setup in README.txt):
    python auto_scout.py config.json

What it does, in plain words:
  1. For each match in config.json it gets the video clip (a file, or just that
     part of a YouTube video).
  2. It looks at a few frames every second and finds robots and balls.
  3. It follows each one (the "tracker").
  4. It counts: balls that go into a goal, times a robot is tipped over, and
     whether a robot ends parked.
  5. It saves the numbers in results.json and (if you ask) sends them to your
     website, where they show up in Prescout under "Video scouting".

These numbers are ROUGH ESTIMATES. They are good for "what could happen at this
event", not for exact scores.
"""
import json, sys, os, time, subprocess, tempfile, urllib.request, urllib.error, hashlib
import cv2


# ----------------------------------------------------------------------------
# PART 1: THE "EYES"  (a detector says what is in one picture)
# A detector returns a list like:
#   [{"cls": "ball", "box": (x1, y1, x2, y2)}, {"cls": "robot", ...}, {"cls": "tipped", ...}]
# ----------------------------------------------------------------------------
class YoloDetector:
    """Uses the model you trained in Roboflow (a file like best.pt)."""
    def __init__(self, model_path, imgsz=640, conf=0.35):
        from ultralytics import YOLO          # installed on your laptop, see README
        self.model = YOLO(model_path)
        self.imgsz, self.conf = imgsz, conf
        self.names = self.model.names          # {0: "ball", 1: "robot", ...}

    def detect(self, frame):
        res = self.model.predict(frame, imgsz=self.imgsz, conf=self.conf, verbose=False)[0]
        out = []
        for b in res.boxes:
            name = str(self.names[int(b.cls[0])]).lower()
            if "tip" in name:
                cls = "tipped"
            elif "ball" in name or "fuel" in name or "artifact" in name or "piece" in name:
                cls = "ball"
            elif "robot" in name or "bot" in name:
                cls = "robot"
            else:
                continue
            x1, y1, x2, y2 = [float(v) for v in b.xyxy[0]]
            out.append({"cls": cls, "box": (x1, y1, x2, y2)})
        return out


class ColorDetector:
    """A stand-in 'eyes' that only looks at colors. Used to TEST this program
    with a fake video (see make_test_video.py). It is not for real matches."""
    RANGES = {  # name: (low HSV, high HSV)
        "ball":   ((5, 150, 150), (20, 255, 255)),     # orange
        "robot":  ((100, 120, 80), (130, 255, 255)),   # blue
        "tipped": ((25, 120, 120), (35, 255, 255)),    # yellow = "on its side"
    }

    def detect(self, frame):
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        out = []
        for cls, (lo, hi) in self.RANGES.items():
            mask = cv2.inRange(hsv, lo, hi)
            cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for c in cnts:
                if cv2.contourArea(c) < 20:
                    continue
                x, y, w, h = cv2.boundingRect(c)
                out.append({"cls": cls, "box": (x, y, x + w, y + h)})
        return out


# ----------------------------------------------------------------------------
# PART 2: THE "MEMORY"  (a tracker remembers which thing is which)
# Each thing it sees gets an id number. Next frame, a thing close to where an
# old one was gets the SAME id. This is the "match by nearest point" idea.
# ----------------------------------------------------------------------------
class Tracker:
    def __init__(self, max_dist, max_missed=6):
        self.max_dist, self.max_missed = max_dist, max_missed
        self.tracks, self.next_id = {}, 1

    def update(self, dets, step):
        """dets: list of dicts with 'cx','cy'. Returns the list with 'id' added."""
        free = set(self.tracks)
        for d in dets:
            best, best_d = None, self.max_dist
            for tid in free:
                t = self.tracks[tid]
                dist = ((t["cx"] - d["cx"]) ** 2 + (t["cy"] - d["cy"]) ** 2) ** 0.5
                if dist < best_d:
                    best, best_d = tid, dist
            if best is None:
                best = self.next_id; self.next_id += 1
                self.tracks[best] = {"missed": 0}
            else:
                free.discard(best)
            self.tracks[best].update(cx=d["cx"], cy=d["cy"], missed=0)
            d["id"] = best
        for tid in list(free):
            self.tracks[tid]["missed"] += 1
            if self.tracks[tid]["missed"] > self.max_missed:
                del self.tracks[tid]
        return dets


def inside(cx, cy, rect, w, h):
    """rect is (x1, y1, x2, y2) as FRACTIONS of the picture (0 to 1)."""
    x1, y1, x2, y2 = rect
    return x1 * w <= cx <= x2 * w and y1 * h <= cy <= y2 * h


# ----------------------------------------------------------------------------
# PART 3: WATCH ONE MATCH AND COUNT
# ----------------------------------------------------------------------------
def analyze_clip(cap, detector, seg, cfg, start_sec, end_sec):
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    W = cap.get(cv2.CAP_PROP_FRAME_WIDTH); H = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
    sample_fps = cfg.get("sample_fps", 5)
    step = max(1, round(fps / sample_fps))
    auto_s = cfg.get("auto_seconds", 30)
    gap_s = cfg.get("transition_seconds", 8)
    lead = seg.get("lead_in", cfg.get("lead_in", 0))        # seconds before the match really starts
    goals = cfg.get("goal_zones", [])
    park = cfg.get("park_zone")
    starts = cfg.get("start_zones", [])                     # one per team, same order as seg["teams"]
    teams = seg.get("teams", [])
    assign_window = cfg.get("assign_seconds", 3)
    min_dim = max(W, H)

    robots = Tracker(max_dist=0.10 * min_dim)
    balls = Tracker(max_dist=0.07 * min_dim)
    team_of = {}                                            # robot track id -> team
    last_pos = {}                                           # robot track id -> (cx, cy, rel_time)
    tip_streak, not_tip, tip_count = {}, {}, {}
    in_goal, counted = {}, set()
    score = {t: {"auto": 0, "teleop": 0, "tips": 0, "parked": 0} for t in teams}
    unknown = 0

    cap.set(cv2.CAP_PROP_POS_MSEC, start_sec * 1000)
    n = 0
    while True:
        t_sec = start_sec + n / fps
        if t_sec > end_sec:
            break
        ok, frame = cap.read()
        if not ok:
            break
        n += 1
        if (n - 1) % step:
            continue
        rel = t_sec - start_sec - lead                      # seconds since the match really started
        dets = detector.detect(frame)
        for d in dets:
            x1, y1, x2, y2 = d["box"]; d["cx"], d["cy"] = (x1 + x2) / 2, (y1 + y2) / 2

        rob = robots.update([d for d in dets if d["cls"] in ("robot", "tipped")], step)
        bal = balls.update([d for d in dets if d["cls"] == "ball"], step)

        for r in rob:
            rid = r["id"]
            last_pos[rid] = (r["cx"], r["cy"], rel)
            # Which team is this robot? Whichever start box it is standing in at the start.
            if rid not in team_of and -2 <= rel <= assign_window:
                for i, z in enumerate(starts):
                    if i < len(teams) and teams[i] not in team_of.values() and inside(r["cx"], r["cy"], z, W, H):
                        team_of[rid] = teams[i]; break
            # Tips: count each time a robot goes from "upright" to "tipped" and stays 2 samples.
            if r["cls"] == "tipped":
                tip_streak[rid] = tip_streak.get(rid, 0) + 1; not_tip[rid] = 0
                if tip_streak[rid] == 2 and rel >= 0:
                    tip_count[rid] = tip_count.get(rid, 0) + 1
            else:
                not_tip[rid] = not_tip.get(rid, 0) + 1
                if not_tip[rid] >= 2:
                    tip_streak[rid] = 0

        if rel >= 0:
            for b in bal:
                bid = b["id"]
                if bid in counted:
                    continue
                if any(inside(b["cx"], b["cy"], g, W, H) for g in goals):
                    in_goal[bid] = in_goal.get(bid, 0) + 1
                    if in_goal[bid] >= 2:                   # in the goal for 2 looks in a row = scored
                        counted.add(bid)
                        # Give the point to the closest robot.
                        best, best_d = None, 1e9
                        for r in rob:
                            dd = ((r["cx"] - b["cx"]) ** 2 + (r["cy"] - b["cy"]) ** 2) ** 0.5
                            if dd < best_d: best, best_d = r["id"], dd
                        team = team_of.get(best)
                        if team is None:
                            unknown += 1
                        elif rel <= auto_s:
                            score[team]["auto"] += 1
                        elif rel >= auto_s + gap_s:
                            score[team]["teleop"] += 1
                        else:
                            score[team]["auto"] += 1        # balls during the short gap count with auto
                else:
                    in_goal[bid] = 0

    # Tips per team
    for rid, c in tip_count.items():
        t = team_of.get(rid)
        if t: score[t]["tips"] += c
    # Parked: where was each robot last seen?
    if park:
        for rid, (cx, cy, rel) in last_pos.items():
            t = team_of.get(rid)
            if t and inside(cx, cy, park, W, H):
                score[t]["parked"] = 1
    found = sorted(set(team_of.values()))
    return score, found, unknown


# ----------------------------------------------------------------------------
# PART 4: GET THE VIDEO (a file, or just one piece of a YouTube video)
# ----------------------------------------------------------------------------
def get_clip(video, start, end, tmpdir, ytdlp="yt-dlp", cookies=None):
    """Returns (path, clip_start, clip_end) for cv2 to open."""
    if video.startswith("http"):
        out = os.path.join(tmpdir, "clip_%d.mp4" % start)
        a, b = sec_to_hms(max(0, start - 5)), sec_to_hms(end + 5)
        cmd = [ytdlp, "-f", "best[height<=480]/best", "--download-sections", f"*{a}-{b}",
               "--force-keyframes-at-cuts", "-o", out, video]
        if cookies and os.path.exists(cookies):             # YouTube sometimes asks "are you a robot?" on GitHub
            cmd[1:1] = ["--cookies", cookies]
        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError:
            raise SystemExit("Could not download that part of the video. If it says 'confirm you are not a bot', "
                             "see the YOUTUBE BLOCKED part of README.txt.")
        return out, 5 if start >= 5 else start, 5 + (end - start)
    return video, start, end


def sec_to_hms(s):
    s = int(s); return "%d:%02d:%02d" % (s // 3600, (s % 3600) // 60, s % 60)


def parse_time(v):
    """Accepts 5025, "5025", "1:23:45" or "23:45"."""
    if isinstance(v, (int, float)): return float(v)
    parts = [float(x) for x in str(v).split(":")]
    sec = 0
    for p in parts: sec = sec * 60 + p
    return sec


# ----------------------------------------------------------------------------
# PART 5: SEND TO YOUR WEBSITE (optional)
# ----------------------------------------------------------------------------
def to_fs(v):
    return {"stringValue": str(v)}


def upload(rows, fb):
    base = "https://firestore.googleapis.com/v1/projects/%s/databases/(default)/documents/submissions/" % fb["projectId"]
    ok = 0
    for doc_id, row in rows:
        body = json.dumps({"fields": {k: to_fs(v) for k, v in row.items()}}).encode()
        req = urllib.request.Request(base + doc_id + "?key=" + fb["apiKey"], data=body, method="PATCH",
                                     headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=30); ok += 1
        except urllib.error.URLError as e:
            print("  could not upload", doc_id, e)
    return ok


# ----------------------------------------------------------------------------
# MATCH LIST FROM A TEXT FILE  (same lines you paste into the Match Watcher page)
#   1:23:45 Q12 14623 254 9999 111
# ----------------------------------------------------------------------------
def read_chapters(path, match_seconds):
    import re
    out = []
    for line in open(path, encoding="utf-8"):
        m = re.match(r"^\s*(?:(\d{1,2}):)?(\d{1,3}):(\d{2})\s*[-:]?\s*(.*)$", line)
        if not m:
            continue
        start = int(m.group(1) or 0) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
        rest = m.group(4).strip()
        label = rest.split()[0] if rest else "match"
        teams = [t for t in re.findall(r"\b\d{3,6}\b", rest) if t != label]
        out.append({"label": label, "start": start, "end": start + match_seconds, "teams": teams})
    return out


# ----------------------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------------------
def main(cfg_path):
    cfg = json.load(open(cfg_path))
    if cfg.get("chapters_file"):
        cfg["matches"] = cfg.get("matches", []) + read_chapters(cfg["chapters_file"], cfg.get("match_seconds", 180))
    followed = set(str(t) for t in cfg.get("followed_teams", []))
    game = cfg.get("game", "ftc").lower()
    det = cfg.get("detector", "yolo")
    detector = ColorDetector() if det == "color" else YoloDetector(cfg["model"], cfg.get("imgsz", 640))
    rows, report = [], []
    tmp = tempfile.mkdtemp()
    for seg in cfg["matches"]:
        teams = [str(t) for t in seg.get("teams", [])]
        if followed and not (followed & set(teams)):
            continue                                      # skip matches with none of our teams
        label = str(seg["label"])
        print("Watching", label, "...")
        start, end = parse_time(seg["start"]), parse_time(seg["end"])
        path, s, e = get_clip(seg.get("video", cfg["video"]), start, end, tmp, cfg.get("yt_dlp", "yt-dlp"), cfg.get("cookies"))
        cap = cv2.VideoCapture(path)
        t0 = time.time()
        score, found, unknown = analyze_clip(cap, detector, seg, cfg, s, e)
        cap.release()
        print("  done in %.0fs. Robots matched to teams: %s. Goals we could not give to a team: %d" % (time.time() - t0, found or "none", unknown))
        for team, sc in score.items():
            if followed and team not in followed:
                continue
            row = {"profileId": "video-scouting", "profileName": "Video scouting", "gameType": game,
                   "source": "video", "video_auto": "1", "team": team, "match": label,
                   "auto_scored": sc["auto"], "teleop_scored": sc["teleop"], "tips": sc["tips"], "parked": sc["parked"],
                   "video_url": seg.get("video", cfg["video"]) if str(seg.get("video", cfg["video"])).startswith("http") else "",
                   "video_notes": "auto-detected (rough estimate)"}
            did = "video_auto_" + hashlib.sha1((team + "|" + label + "|" + str(cfg.get("video"))).encode()).hexdigest()[:12]
            rows.append((did, row)); report.append(row)
    json.dump(report, open(cfg.get("output", "results.json"), "w"), indent=2)
    print("Saved %d row(s) to %s" % (len(report), cfg.get("output", "results.json")))
    if cfg.get("upload") and cfg.get("firebase"):
        print("Uploaded", upload(rows, cfg["firebase"]), "row(s) to your website.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python auto_scout.py config.json"); sys.exit(1)
    main(sys.argv[1])
