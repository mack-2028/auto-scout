=====================================================================
RUN IT ON GITHUB INSTEAD OF YOUR LAPTOP (no command window, no installs)
=====================================================================
It works like "Build Full APK": you press a button on GitHub and GitHub's computers do the watching.
Only the model training (Roboflow) and drawing boxes happen on your side.

 1. On GitHub make a NEW repository called  auto-scout  (public is fine).
 2. Upload these files to it (drag them in, Commit):
        auto_scout.py     config.json     chapters.txt     best.pt
    config.json = copy of config.example.json with your settings. chapters.txt = your match times.
    best.pt     = the model file you downloaded from Roboflow (after training).
    Set "upload": true in config.json so the numbers go to your website.
 3. Add the workflow file: in the repo click  Add file > Create new file.  For the name type exactly
        .github/workflows/auto-scout.yml
    and paste in everything from  github-version/auto-scout.yml  (in this folder). Commit.
 4. Draw the boxes: double-click  draw-zones.html  , open a screenshot of the video at the start of a match,
    drag the boxes, press Copy, and paste the result into config.json on GitHub (click the pencil to edit).
 5. Run it: repo > Actions tab > "Auto Scout" > Run workflow. It takes a while (each match a few minutes).
    The numbers appear on your website in Prescout under "Video scouting".
    results.json is also saved on the run page, under "Artifacts".

 To change matches or teams later: edit chapters.txt or config.json on GitHub, then Run workflow again.

 YOUTUBE BLOCKED?  GitHub's computers are sometimes refused by YouTube ("confirm you're not a bot").
 This is the biggest risk of the GitHub way, and I could not test it. If the run fails at the download:
   a) Install the browser add-on "Get cookies.txt LOCALLY", open youtube.com while signed in, export cookies.
      USE A SPARE GOOGLE ACCOUNT, not your main one. Cookies work like a password.
   b) On GitHub: repo > Settings > Secrets and variables > Actions > New repository secret.
      Name: YT_COOKIES   Value: paste the whole cookies text.
   c) In config.json add the line   "cookies": "cookies.txt",
   d) Run workflow again.
 If it still fails, use the laptop way below (.bat files), which downloads from your own home internet.

NO COMMAND WINDOW NEEDED: just double-click the numbered files in this folder, in order.
   1-install-basic.bat        (once)
   2-test-with-fake-match.bat (checks that everything works, no model needed)
   3-install-ai-part.bat      (once, only when you have a trained model best.pt)
   4-draw-boxes.bat           (draw the start / goal / park boxes on a picture)
   5-run-auto-scout.bat       (watches your matches and saves the numbers)
If Windows shows a blue "protected your PC" box, click More info, then Run anyway.
The older typed commands below do the same thing; you can ignore them.

AUTO SCOUT - SETUP (do this once)
==================================
This program watches match videos on your laptop and writes down ROUGH estimates:
balls scored in auto and teleop, times tipped over, and parked or not.
It is for guessing what could happen at an event, not for exact scores.

A. INSTALL (once)
   1. Install Python from python.org (tick "Add Python to PATH").
   2. Open the Start menu, type "cmd", press Enter. In the black window type each line + Enter:
        pip install opencv-python ultralytics yt-dlp
        winget install ffmpeg
      (Your laptop has no NVIDIA card, so this runs on the processor. That is fine. It is slower.)

B. TEACH IT YOUR GAME (once per game, this is the long part)
   1. Make a free account at roboflow.com. Make a new "Object Detection" project.
   2. Upload frames from 2 or 3 match videos (Roboflow can cut a video into frames for you).
   3. Draw boxes and give each a name. Use these EXACT names:
        robot     = a robot standing normally
        tipped    = a robot lying on its side
        ball      = a scoring piece
      Label about 150 to 300 pictures. More = better.
   4. Click "Train" and choose "YOLO11 Nano" (small and fast). When it finishes,
      download the model as "YOLOv11 / PyTorch" and save the file "best.pt" in this folder.

C. MAKE YOUR CONFIG (once per video)
   1. Copy config.example.json to config.json. Put your video link in "video".
   2. Put your match times in chapters.txt (copy chapters.example.txt). One line per match:
          1:23:45 Q12 14623 254 9999 111
      time, match name, then the team numbers: first the red teams, then the blue teams.
      (Same lines as the "Jump to a match" box on the Match Watcher page.)
   3. Put the teams you care about in "followed_teams". Matches without them are skipped.
   4. Draw the boxes:   python pick_zones.py config.json 1:23:40
      A picture opens. Drag boxes around each robot's start spot, each goal, and the park zone.

D. RUN IT
      python auto_scout.py config.json
   It prints what it watched and saves results.json.
   To send the numbers to your website, set "upload": true in config.json.
   They show up in Prescout under "Video scouting" (marked "auto-detected").

E. TEST IT FIRST WITH A FAKE MATCH (no model needed)
      python make_test_video.py
      python auto_scout.py test_config.json
   The right answer is printed by make_test_video.py. For team 14623 you should get:
   auto 4, teleop 2, tips 1, parked 1.

THINGS TO KNOW
 - It only knows what the camera shows. When the stream cuts to a replay or another angle, counts will be off.
 - Matches take a few minutes each on your laptop. Close other programs first (memory is tight).
 - Only part of the video is downloaded (the matches you listed), not the whole 11 hours.
 - Downloading YouTube videos may be against YouTube's rules. Use it for your own team's scouting only.
 - Start with 2 or 3 matches and look at the numbers before you trust it.
