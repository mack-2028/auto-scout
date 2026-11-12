"""Makes a FAKE 'match' video so we can test auto_scout.py without a real match.
Blue squares = robots, orange dots = balls, a yellow square = a robot on its side.
Run:  python make_test_video.py   ->  fake_match.mp4 and fake_truth.json
"""
import cv2, numpy as np, json
W, H, FPS, SECS = 640, 360, 30, 60
out = cv2.VideoWriter("fake_match.mp4", cv2.VideoWriter_fourcc(*"mp4v"), FPS, (W, H))
GOAL = (560, 100, 630, 260)                       # goal on the right side (pixels)
YROW = {"A": 150, "B": 250}                       # each robot stays on its own row


def robot_x(t):                                   # both robots drive right, then stop near the goal
    return min(80 + 10 * t, 480)


# (robot, time the ball is thrown). A ball reaches the goal about 3 seconds later.
shots = [("A", 3), ("A", 9), ("A", 18), ("B", 14), ("A", 25), ("B", 40), ("A", 45), ("A", 50)]
truth = {"A": {"auto": 0, "teleop": 0, "tips": 1, "parked": 1}, "B": {"auto": 0, "teleop": 0, "tips": 0, "parked": 0}}
for who, t0 in shots:
    truth[who]["auto" if t0 + 3 <= 30 else "teleop"] += 1

for f in range(FPS * SECS):
    t = f / FPS
    img = np.full((H, W, 3), (40, 120, 40), np.uint8)                 # green field
    cv2.rectangle(img, GOAL[:2], GOAL[2:], (60, 60, 60), -1)           # gray goal
    x = int(robot_x(t))
    for who in "AB":
        tipped = (who == "A" and 33 <= t <= 37)                        # A lies on its side for 4 seconds
        color = (0, 230, 230) if tipped else (200, 60, 30)             # BGR: yellow vs blue
        y = YROW[who]
        cv2.rectangle(img, (x - 25, y - 25), (x + 25, y + 25), color, -1)
    for who, t0 in shots:
        y = YROW[who]
        if t0 <= t < t0 + 4:                                           # ball flies to the goal
            k = (t - t0) / 4
            sx = robot_x(t0)
            bx = sx + (595 - sx) * k
            cv2.circle(img, (int(bx), y), 8, (0, 140, 255), -1)        # orange
        elif t0 + 4 <= t < t0 + 8:
            cv2.circle(img, (595, y), 8, (0, 140, 255), -1)            # sits in the goal for a while
    out.write(img)
out.release()
json.dump(truth, open("fake_truth.json", "w"))
print("made fake_match.mp4; the right answer is:", truth)
