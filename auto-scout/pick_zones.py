"""
PICK ZONES  -  you draw boxes on a picture from the video; this saves them in config.json.

Run:   python pick_zones.py config.json 0:05:30
       (the time is any moment in the video when the match is just starting,
        so you can see where the robots stand)

It opens a picture. For each box it asks, DRAG a rectangle with the mouse, then press
ENTER (or SPACE). Press C to skip a box.
  1. START boxes: one box around where each robot starts (red 1, red 2, blue 1, blue 2 ...)
  2. GOAL boxes:  around each scoring goal (press ESC when you have no more goals)
  3. PARK box:    around the parking / end zone
"""
import sys, json, os, subprocess, tempfile
import cv2


def grab_frame(video, at_sec):
    if video.startswith("http"):
        tmp = os.path.join(tempfile.mkdtemp(), "f.mp4")
        a = "%d:%02d:%02d" % (at_sec // 3600, (at_sec % 3600) // 60, at_sec % 60)
        b = "%d:%02d:%02d" % ((at_sec + 6) // 3600, ((at_sec + 6) % 3600) // 60, (at_sec + 6) % 60)
        subprocess.run(["yt-dlp", "-f", "best[height<=720]/best", "--download-sections", f"*{a}-{b}", "-o", tmp, video], check=True)
        video, at_sec = tmp, 1
    cap = cv2.VideoCapture(video)
    cap.set(cv2.CAP_PROP_POS_MSEC, at_sec * 1000)
    ok, frame = cap.read()
    if not ok:
        raise SystemExit("Could not read that moment of the video.")
    return frame


def to_seconds(v):
    sec = 0
    for p in str(v).split(":"):
        sec = sec * 60 + float(p)
    return int(sec)


def pick(frame, title):
    r = cv2.selectROI(title, frame, showCrosshair=False)
    cv2.destroyAllWindows()
    x, y, w, h = r
    if w == 0 or h == 0:
        return None
    H, W = frame.shape[:2]
    return [round(x / W, 3), round(y / H, 3), round((x + w) / W, 3), round((y + h) / H, 3)]


def main():
    cfg_path, at = sys.argv[1], to_seconds(sys.argv[2])
    cfg = json.load(open(cfg_path))
    frame = grab_frame(cfg["video"], at)
    n = int(input("How many robots are in a match (4 for FTC, 6 for FRC)? ") or 4)
    names = (["Red 1", "Red 2", "Red 3"] + ["Blue 1", "Blue 2", "Blue 3"]) if n == 6 else ["Red 1", "Red 2", "Blue 1", "Blue 2"]
    cfg["start_zones"] = [pick(frame, "START box for " + nm) or [0, 0, 0, 0] for nm in names]
    goals = []
    while True:
        g = pick(frame, "GOAL box (ESC / empty = no more goals)")
        if not g:
            break
        goals.append(g)
    cfg["goal_zones"] = goals
    cfg["park_zone"] = pick(frame, "PARK box (empty = skip)")
    json.dump(cfg, open(cfg_path, "w"), indent=2)
    print("Saved the boxes in", cfg_path)


if __name__ == "__main__":
    main()
