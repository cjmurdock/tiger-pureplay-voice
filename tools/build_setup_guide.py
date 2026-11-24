"""Builds docs/Tiger_Setup_Guide.pdf. Run from the Tiger folder:

    pip install reportlab
    python tools/build_setup_guide.py

Edit the text below and run it again whenever setup changes.
"""
import os

from reportlab.lib.colors import Color, white
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

GREEN = Color(0.121569, 0.435294, 0.262745)
LIGHT = Color(0.917647, 0.956863, 0.933333)
CODE_BG = Color(0.94902, 0.94902, 0.94902)
GREY = Color(0.333333, 0.333333, 0.333333)

TITLE = ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=24, leading=28,
                       textColor=GREEN, alignment=TA_CENTER, spaceAfter=4)
INTRO = ParagraphStyle("intro", fontName="Helvetica", fontSize=10.5, leading=14, textColor=GREY)
H = ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=13.5, leading=17, textColor=GREEN,
                   spaceBefore=12, spaceAfter=5, keepWithNext=1)
BODY = ParagraphStyle("body", fontName="Helvetica", fontSize=9.5, leading=12.5)
BULLET = ParagraphStyle("bullet", parent=BODY, leftIndent=9, bulletIndent=0, spaceAfter=2.5)
STEP_TITLE = ParagraphStyle("st", parent=BODY, fontName="Helvetica-Bold", spaceAfter=2)
STEP_NUM = ParagraphStyle("sn", fontName="Helvetica-Bold", fontSize=12, leading=14,
                          textColor=white, alignment=TA_CENTER)
CODE = ParagraphStyle("code", fontName="Courier", fontSize=8.8, leading=11, backColor=CODE_BG,
                      borderPadding=(4, 4, 4, 4), spaceBefore=5, spaceAfter=7, leftIndent=4)
FOOTER = "Tiger voice control for Pureplay \u00b7 Windows \u00b7 Uses the Pureplay Accessory API and " \
         "Vosk offline speech recognition"


def bullets(items):
    return [Paragraph(t, BULLET, bulletText="\u2022") for t in items]


def code(text):
    return Paragraph(text.replace(" ", "&nbsp;"), CODE)


def step(n, title, *parts):
    cell = [Paragraph(title, STEP_TITLE)]
    for p in parts:
        cell.append(p if not isinstance(p, str) else Paragraph(p, BODY))
    t = Table([[Paragraph(str(n), STEP_NUM), cell]], colWidths=[28.8, 493.2])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), GREEN), ("BACKGROUND", (1, 0), (1, 0), LIGHT),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (1, 0), (1, 0), 8), ("RIGHTPADDING", (1, 0), (1, 0), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    return KeepTogether([t, Spacer(1, 6)])


def update_box():
    """'Already using Tiger?' note at the top, for people updating rather than installing."""
    text = [Paragraph("Already using Tiger? To update", STEP_TITLE),
            Paragraph("Open <b>Tiger Settings</b>, go to the <b>Updates</b> tab and press <b>Update "
                      "now</b> (or double-click <b>update.bat</b> in your Tiger folder). It downloads the "
                      "latest version, closes and restarts Tiger for you, and keeps your settings "
                      "(config.json), your Pureplay pairing (token.json) and the speech model. You don't "
                      "need anything else in this guide.", BODY),
            Spacer(1, 4),
            Paragraph("<b>No update.bat in your folder</b> (copies from before 24 November 2026)? Update "
                      "by hand once: close Tiger, download the ZIP from GitHub, open the "
                      "<b>tiger-pureplay-voice-main</b> folder inside it, and copy everything in it "
                      "<b>except config.json</b> into your Tiger folder, choosing Replace when Windows "
                      "asks. Don't delete the old folder first (the speech model isn't in the download), "
                      "and don't run setup.bat again. After that, the Updates tab does it for you.", BODY)]
    t = Table([[text]], colWidths=[522])
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1.2, GREEN), ("BACKGROUND", (0, 0), (-1, -1), white),
        ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    return t


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(GREY)
    canvas.drawString(43.2, 32.36, FOOTER)
    canvas.drawRightString(612 - 43.2, 32.36, f"Page {doc.page}")
    canvas.restoreState()


def story():
    s = [Paragraph("Tiger Setup Guide", TITLE),
         Paragraph("Voice control for Pureplay golf. Say <b>\u201cTiger\u201d</b> and ask naturally: "
                   "\u201cTiger, give me a seven iron.\u201d Runs offline on the sim PC and doesn't use "
                   "the graphics card.", INTRO),
         Spacer(1, 8), update_box(),
         Paragraph("What you need", H)]
    s += bullets(["A Windows PC running Pureplay.",
                  "A USB microphone near the hitting area. A 360\u00b0 conference mic (for example TONOR "
                  "G11 or TONOR TM20) works well in a sim room.",
                  "Speakers (Tiger talks back).",
                  "Internet for setup and updates (Tiger itself runs offline)."])
    s.append(Paragraph("Install", H))
    s += [
        step(1, "Install Python",
             "Download Python 3.10 or newer from <b>python.org</b> and run the installer. On the first "
             "screen, tick <b>Add python.exe to PATH</b>, then Install Now."),
        step(2, "Put Tiger in its own folder",
             "Unzip the Tiger folder somewhere permanent. These instructions assume <b>C:\\Tiger</b>."),
        step(3, "Run setup",
             "Double-click <b>setup.bat</b>. It installs what Tiger needs, downloads the speech model "
             "(about 40 MB) and lists your microphones. If Windows warns about an unknown app, choose "
             "More info, then Run anyway."),
        step(4, "Pick your microphone in Tiger Settings",
             "Double-click <b>Tiger Settings.bat</b>. On the <b>Microphone</b> tab, choose your mic, "
             "talk from where you stand to hit and watch the level bar move, then press <b>Use this "
             "microphone</b>. While you're there, pick a voice on the <b>Voice</b> tab and enter your "
             "carry distances on the <b>Distances</b> tab, or come back to them later."),
        step(5, "Turn on Pureplay's accessory settings",
             "In Pureplay, open <b>Settings &gt; Accessories</b> and set: <b>Allow apps from: This PC</b> "
             "\u00b7 <b>Ask about new apps: on</b> \u00b7 <b>Let Apps Change Aim and Club: on</b>. "
             "Press Apply."),
        step(6, "Start Tiger and approve it",
             "With Pureplay open, double-click <b>run_tiger.bat</b>. Pureplay shows <b>Allow \u201cTiger "
             "Voice Control\u201d?</b> Click <b>Aim and club</b> first, then <b>Allow</b>. If you pick "
             "Read only, Tiger can't change clubs or aim: open Tiger Settings, go to the <b>Status</b> "
             "tab and follow <b>Re-pair with Pureplay</b>."),
        step(7, "Try it",
             "Stand at the tee and say <b>\u201cTiger, give me a seven iron.\u201d</b> Tiger switches the "
             "club and says it back. See <b>Tiger_Voice_Commands.pdf</b> for everything you can say."),
    ]
    s.append(Paragraph("Tiger Settings", H))
    s.append(Paragraph("Open <b>Tiger Settings.bat</b> any time. Changes are saved to config.json "
                       "straight away and a running Tiger uses them within a second, so there's no need "
                       "to restart it.", BODY))
    s.append(Spacer(1, 4))
    s += bullets([
        "<b>Voice</b>: every Windows voice on the PC. Double-click one to hear it, then press <b>Use this "
        "voice</b>. The <b>Speed</b> and <b>Volume</b> sliders save as you move them. You can also say "
        "\u201cTiger, switch to Linda\u201d, \u201cTiger, next voice\u201d, \u201cTiger, talk "
        "faster\u201d or \u201cTiger, speak up\u201d.",
        "<b>Microphone</b>: the mic Tiger listens on, a live level meter, and how sure Tiger must be "
        "before acting. Move that slider toward Strict if Tiger acts on things you didn't say, or toward "
        "Relaxed if it ignores you.",
        "<b>Distances</b>: your carry for each club, so \u201cwhat should I hit from one fifty\u201d picks "
        "the right one. The numbers that come with Tiger are only placeholders. Leave clubs you don't "
        "carry blank.",
        "<b>Status</b>: whether Tiger is running and how it's paired with Pureplay, a <b>Re-pair</b> "
        "button, and shortcuts to the Tiger folder and config.json.",
        "<b>Updates</b>: checks for a new version when the window opens. <b>Update now</b> installs it "
        "and restarts Tiger, keeping all your settings."])
    s.append(Paragraph("Other settings (config.json)", H))
    s += bullets([
        "<b>Callouts</b>: <b>\"announce\"</b> controls the \u201cyou're up, 150 to the pin\u201d callouts. "
        "Set <b>\"shot_result\"</b> to true to hear carry after each shot.",
        "<b>Hotkeys</b>: if you've changed Pureplay's keyboard shortcuts, update <b>\"hotkeys\"</b> to "
        "match.",
        "<b>Units</b>: \"yards\" or \"metres\".",
        "<b>Lights</b>: Home Assistant users can enable <b>\"home_assistant\"</b> for \u201cTiger, lights "
        "down\u201d.",
        "If config.json gets a typo, Tiger keeps its last good settings and says where the mistake is. "
        "The previous version is saved as <b>config.backup.json</b>."])
    s.append(Paragraph("Start Tiger with your sim (optional)", H))
    s.append(Paragraph("If you start your sim with a .bat file, add this line after the line that starts "
                       "Pureplay. Tiger opens minimized and waits for Pureplay. Only one copy of Tiger "
                       "runs at a time, so it's safe if the .bat is run twice.", BODY))
    s.append(code('start "Tiger" /min "C:\\Tiger\\run_tiger.bat"'))
    s.append(Paragraph("Troubleshooting", H))
    s += bullets([
        "<b>Test without a mic</b>: <b>run_tiger.bat --type</b> lets you type commands (like \u201cseven "
        "iron\u201d) instead of speaking.",
        "<b>It doesn't hear you</b>: check the level bar on the Microphone tab of Tiger Settings, raise the "
        "mic level in Windows Sound settings, move the mic closer, or run <b>run_tiger.bat --debug</b> to "
        "see what it hears.",
        "<b>It acts on things you didn't say</b>: move the slider on the Microphone tab toward Strict "
        "(for example 0.7).",
        "<b>Tiger Settings doesn't open</b>: run the Python installer again, choose <b>Modify</b> and tick "
        "<b>tcl/tk and IDLE</b>.",
        "<b>Club and aim work, but keys like mulligan don't</b>: run <b>python tiger.py --list-windows</b> "
        "and put part of Pureplay's window title in <b>\"game_window_title\"</b>.",
        "<b>\u201cI'm not connected to Pureplay\u201d</b>: check step 5, and that Pureplay is running on the "
        "same PC.",
        "<b>Careful when clicking Pureplay</b>: clicking on the course moves your aim. Click the top or "
        "bottom bars instead.",
        "<b>Tiger shows \u201cRead only\u201d in Settings &gt; Accessories, or says it's paired read "
        "only</b>: Tiger was approved without aim and club control. In Pureplay, click <b>Remove</b> next "
        "to Tiger in Settings &gt; Accessories. Then in Tiger Settings, press <b>Re-pair Tiger</b> on the "
        "Status tab and choose <b>Aim and club</b> before <b>Allow</b>. Nothing extra needs installing."])
    return s


def main():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = os.path.join(here, "docs", "Tiger_Setup_Guide.pdf")
    doc = SimpleDocTemplate(out, pagesize=letter, leftMargin=43.2, rightMargin=43.2,
                            topMargin=36, bottomMargin=54, title="Tiger Setup Guide",
                            author="", subject="", creator="")
    doc.build(story(), onFirstPage=footer, onLaterPages=footer)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
