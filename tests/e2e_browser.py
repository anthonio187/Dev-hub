"""Browser end-to-end test for DevX (two users talking to each other).

    pip install playwright && python -m playwright install chromium
    BASE_URL=http://localhost:5000 python tests/e2e_browser.py   (use a fresh database first)

Set HEADLESS=0 to watch it run. Screenshots are written to ./e2e-shots/.
"""

import os
import re
import struct
import sys
import uuid
import zlib

from playwright.sync_api import expect, sync_playwright

BASE = os.environ.get("BASE_URL", "http://localhost:5000").rstrip("/")
HEADLESS = os.environ.get("HEADLESS", "1") != "0"
SHOTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "e2e-shots")
os.makedirs(SHOTS, exist_ok=True)


def make_png(path, rgb=(29, 155, 240)):
    w = h = 64
    raw = b"".join(b"\x00" + bytes(rgb) * w for _ in range(h))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")
    with open(path, "wb") as fh:
        fh.write(png)
    return path


def shot(page, name):
    page.screenshot(path=os.path.join(SHOTS, f"{name}.png"), full_page=False)


def signup(page, username, password="password123"):
    page.goto(BASE + "/")
    page.locator("input[name=username]").fill(username)
    if page.locator("input[name=email]").count():
        page.locator("input[name=email]").fill(f"{re.sub(r'[^a-z0-9]', '', username)}@example.com")
    page.locator("input[name=password]").fill(password)
    page.locator("button[type=submit]").click()
    expect(page.locator(".composer textarea").first).to_be_visible(timeout=10000)


def main():
    suffix = uuid.uuid4().hex[:6]
    alice_name = f"alice_{suffix}"
    bob_name = f"bob_{suffix}"
    png = make_png(os.path.join(SHOTS, "pixel.png"))
    png2 = make_png(os.path.join(SHOTS, "pixel2.png"), (255, 120, 80))
    errors = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        bob_ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        alice_ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        bob = bob_ctx.new_page()
        alice = alice_ctx.new_page()
        for page, who in ((bob, "bob"), (alice, "alice")):
            page.on("pageerror", lambda e, who=who: errors.append(f"{who}: {e}"))
            page.on("dialog", lambda d: d.accept())

        print("1. sign up two developers")
        signup(bob, bob_name)
        signup(alice, alice_name)
        expect(alice.locator(".nav-item", has_text="Profile")).to_be_visible()
        shot(alice, "01-home-empty")

        print("2. alice posts with hashtag, mention, and a code snippet")
        alice.locator(".composer textarea").first.fill(f"Shipping my first #DevX feature — cc @{bob_name}")
        alice.locator("button[aria-label='Add code snippet']").click()
        alice.locator(".code-input").fill('console.log("hello devx");')
        alice.locator(".lang-select").select_option("javascript")
        alice.locator(".compose-tools .btn.primary").click()
        post = alice.locator("article.tweet", has_text="Shipping my first")
        expect(post).to_be_visible()
        expect(post.locator(".code-block")).to_contain_text("console.log")
        expect(post.locator(".code-head span")).to_have_text("javascript")

        print("3. alice attaches images and posts")
        alice.locator(".composer input[type=file]").set_input_files([png, png2])
        expect(alice.locator(".thumb")).to_have_count(2, timeout=30000)  # R2 uploads are sequential over the network
        expect(alice.locator(".thumb.busy")).to_have_count(0, timeout=10000)
        alice.locator(".composer textarea").first.fill("Look at the layout 🎨")
        alice.locator(".compose-tools .btn.primary").click()
        img_post = alice.locator("article.tweet", has_text="Look at the layout")
        expect(img_post.locator(".media img")).to_have_count(2)
        shot(alice, "02-alice-post-with-media")

        print("4. bob follows alice, likes, replies, reposts and quotes")
        bob.goto(BASE + "/u/" + alice_name)
        bob.locator(".profile-actions .follow-btn").click()
        expect(bob.locator(".profile-actions .follow-btn")).to_have_text("Following")
        bob.goto(BASE + "/")
        bob_post = bob.locator("article.tweet", has_text="Shipping my first")
        expect(bob_post).to_be_visible()
        bob_post.locator(".act.like").click()
        expect(bob_post.locator(".act.like")).to_have_class("act like on")

        bob_post.locator(".act.reply").click()
        modal = bob.locator(".modal")
        expect(modal).to_be_visible()
        modal.locator(".compose-text").fill("Nice work! 🚀")
        modal.locator(".compose-tools .btn.primary").click()
        expect(bob.locator(".modal")).to_have_count(0)
        expect(bob.locator("article.tweet", has_text="Shipping my first").locator(".act.reply .cnt")).to_have_text("1")

        bob.locator("article.tweet", has_text="Shipping my first").locator(".act.repost").click()
        bob.get_by_role("menuitem", name="Repost").click()
        expect(bob.locator("article.tweet", has_text="Shipping my first").locator(".act.repost")).to_have_class("act repost on")

        bob.locator("article.tweet", has_text="Shipping my first").locator(".act.repost").click()
        bob.get_by_role("menuitem", name="Quote").click()
        bob.locator(".modal .compose-text").fill("Love this approach 💯")
        bob.locator(".modal .compose-tools .btn.primary").click()
        expect(bob.locator(".modal")).to_have_count(0)
        quote_card = bob.locator("article.tweet", has_text="Love this approach")
        expect(quote_card.locator(".quote-card")).to_contain_text("Shipping my first")

        bob.locator("article.tweet", has_text="Shipping my first").first.locator(".act.bookmark").click()
        shot(bob, "03-bob-feed")

        print("5. alice sees notifications and the unread badge")
        alice.reload()
        expect(alice.locator("[data-badge=notifications]")).to_be_visible(timeout=10000)
        alice.goto(BASE + "/notifications")
        expect(alice.locator("article.notif").first).to_be_visible(timeout=15000)
        notif_text = alice.locator("article.notif").all_inner_texts()
        joined = "\n".join(notif_text)
        for needle in ("followed you", "liked your post", "replied to your post", "reposted your post", "quoted your post"):
            assert needle in joined, f"missing notification: {needle}\n{joined}"
        shot(alice, "04-alice-notifications")

        print("6. alice sends a DM with an image; bob receives it")
        alice.goto(BASE + "/messages")
        alice.get_by_role("button", name="New message").click()
        alice.locator("input[placeholder='Username (without @)']").fill(bob_name)
        alice.get_by_role("button", name="Start conversation").click()
        expect(alice).to_have_url(re.compile(r".*/messages/\d+$"))
        alice.locator(".dm-input").fill("Hey Bob! Check this out")
        alice.locator(".dm-input").press("Enter")
        expect(alice.locator(".bubble.mine", has_text="Hey Bob")).to_be_visible()
        alice.locator(".dm-wrap input[type=file]").set_input_files(png)
        expect(alice.locator(".dm-chip")).to_be_visible(timeout=10000)
        alice.locator("button[aria-label=Send]").click()
        expect(alice.locator(".bubble.mine img.dm-img")).to_be_visible(timeout=10000)
        conv_url = alice.url

        bob.reload()
        expect(bob.locator("[data-badge=messages]")).to_be_visible(timeout=10000)
        bob.goto(BASE + "/messages")
        expect(bob.locator(".conv-row", has_text=alice_name)).to_be_visible()
        expect(bob.locator(".conv-row .dot")).to_have_count(1)
        bob.locator(".conv-row", has_text=alice_name).click()
        expect(bob.locator(".bubble.theirs", has_text="Hey Bob")).to_be_visible()
        expect(bob.locator(".bubble.theirs img.dm-img")).to_be_visible()
        shot(bob, "05-bob-dm")

        print("7. live updates: alice's next message appears on bob's open chat without reload")
        alice.goto(conv_url)
        alice.locator(".dm-input").fill("Live update — no refresh needed")
        alice.locator(".dm-input").press("Enter")
        expect(bob.locator(".bubble.theirs", has_text="Live update")).to_be_visible(timeout=10000)

        print("8. bob replies in the DM")
        bob.locator(".dm-input").fill("Looks great, @" + alice_name + " 🔥")
        bob.locator(".dm-input").press("Enter")
        expect(alice.locator(".bubble.theirs", has_text="Looks great")).to_be_visible(timeout=10000)

        print("9. profile settings and profile tabs")
        alice.goto(BASE + "/settings")
        alice.locator("textarea.input").first.fill("Full-stack dev. Ship in public.")
        alice.get_by_role("button", name="Save profile").click()
        expect(alice.locator(".toast", has_text="Profile saved")).to_be_visible()
        tech_input = alice.locator("input[placeholder='Python, Postgres, React, Go']")
        tech_input.fill("Python, Postgres, React")
        alice.get_by_role("button", name="Save profile").click()
        alice.goto(BASE + "/u/" + alice_name)
        expect(alice.locator(".profile-bio")).to_contain_text("Ship in public")
        expect(alice.locator(".chip", has_text="Postgres")).to_be_visible()
        alice.get_by_role("tab", name="Media").click()
        expect(alice.locator("article.tweet", has_text="Look at the layout")).to_be_visible()
        alice.get_by_role("tab", name="Likes").click()
        expect(alice.locator("article.tweet")).to_have_count(0, timeout=10000)
        alice.get_by_role("tab", name="Posts").click()
        shot(alice, "06-alice-profile")

        print("10. search, hashtags, followers list")
        alice.locator(".side-search input").fill("devx")
        alice.keyboard.press("Enter")
        expect(alice).to_have_url(BASE + "/search?q=devx")
        expect(alice.locator("article.tweet", has_text="Shipping my first")).to_be_visible()
        alice.get_by_role("tab", name="People").click()
        expect(alice.locator(".user-row", has_text=bob_name)).to_have_count(0)
        alice.goto(BASE + "/u/" + alice_name + "/followers")
        expect(alice.locator(".user-row", has_text=bob_name)).to_be_visible()

        print("11. bookmarks & deleting a post")
        bob.goto(BASE + "/bookmarks")
        expect(bob.locator("article.tweet", has_text="Shipping my first")).to_be_visible()
        alice.goto(BASE + "/")
        target = alice.locator("article.tweet", has_text="Look at the layout")
        target.locator(".more").click()
        alice.get_by_role("menuitem", name="Delete post").click()
        expect(alice.locator("article.tweet", has_text="Look at the layout")).to_have_count(0, timeout=10000)

        print("12. log out and log back in")
        alice.locator(".account").click()
        alice.get_by_role("menuitem", name="Log out").click()
        expect(alice.locator(".auth-card")).to_be_visible(timeout=10000)
        alice.locator("button.link-btn", has_text="Log in").click()
        alice.locator("input[name=username]").fill(alice_name)
        alice.locator("input[name=password]").fill("password123")
        alice.locator("button[type=submit]").click()
        expect(alice.locator(".composer textarea").first).to_be_visible(timeout=10000)

        print("13. developer features: link npm + GitHub (live APIs), availability, repo preview, directory")
        alice.goto(BASE + "/settings")
        npm_row = alice.locator(".dev-row", has_text="npm")
        expect(npm_row).to_be_visible(timeout=10000)
        npm_row.locator("input").fill("sindresorhus")
        npm_row.get_by_role("button", name="Link account").click()
        expect(alice.locator(".toast", has_text="npm linked")).to_be_visible(timeout=20000)
        gh_row = alice.locator(".dev-row", has_text="GitHub")
        gh_row.locator("input").fill("torvalds")
        gh_row.get_by_role("button", name="Link account").click()
        expect(alice.locator(".verify-box code")).to_have_text(re.compile(r"^devx-[0-9a-f]{8}$"), timeout=20000)
        alice.get_by_role("button", name="Verify ownership").click()
        expect(alice.locator(".toast", has_text="bio")).to_be_visible(timeout=20000)
        alice.locator(".dev-row", has_text="GitHub").get_by_role("button", name="Unlink").click()
        expect(alice.locator(".toast", has_text="GitHub unlinked")).to_be_visible(timeout=10000)
        alice.locator("input[type=checkbox]").check()
        alice.locator("input[placeholder='Freelance backend work, remote roles…']").fill("Remote backend contracts")
        alice.get_by_role("button", name="Save availability").click()
        expect(alice.locator(".toast", has_text="Availability saved")).to_be_visible()

        alice.goto(BASE + "/u/" + alice_name)
        expect(alice.locator(".dev-panel")).to_contain_text("Open to work")
        expect(alice.locator(".dev-panel")).to_contain_text("npm")
        expect(alice.locator(".dev-panel .dev-link").first).to_be_visible()

        alice.goto(BASE + "/")
        alice.locator(".composer textarea").first.fill("Using https://github.com/psf/requests in my new project")
        alice.locator(".compose-tools .btn.primary").click()
        repo_post = alice.locator("article.tweet", has_text="Using https://github.com/psf/requests")
        expect(repo_post.locator(".repo-card")).to_contain_text("psf/requests", timeout=20000)

        alice.goto(BASE + "/devs")
        expect(alice.locator(".user-row", has_text=alice_name)).to_be_visible(timeout=10000)
        alice.locator(".dev-filters input[type=checkbox]").check()
        expect(alice.locator(".user-row", has_text=alice_name)).to_be_visible(timeout=10000)
        alice.locator(".dev-filters input[type=search]").fill("rust")
        expect(alice.locator(".user-row", has_text=alice_name)).to_have_count(0, timeout=10000)
        shot(alice, "08-developers")

        print("14. projects, collaboration requests, file attachments and post editing")
        pdf_path = os.path.join(SHOTS, "spec.pdf")
        with open(pdf_path, "wb") as fh:
            fh.write(b"%PDF-1.4\n% DevX e2e spec\n")
        alice.goto(BASE + "/projects")
        alice.get_by_role("button", name="New project").click()
        modal = alice.locator(".modal")
        modal.get_by_placeholder("e.g. Tiny Compiler").fill(f"Tiny compiler {suffix}")
        modal.get_by_placeholder("rust, wasm, compilers").fill("rust, compilers")
        modal.get_by_placeholder("https://github.com/you/project").fill("https://github.com/psf/requests")
        modal.get_by_role("button", name="Create project").click()
        expect(alice.locator(".proj-title.big")).to_contain_text(f"Tiny compiler {suffix}", timeout=10000)
        pid = re.search(r"/projects/(\d+)", alice.url).group(1)
        expect(alice.locator("a[href*='github.com/psf/requests']").first).to_be_visible()

        bob.goto(BASE + "/projects/" + pid)
        bob.get_by_role("button", name=re.compile(r"Like")).click()
        expect(bob.get_by_role("button", name=re.compile(r"Liked"))).to_be_visible(timeout=10000)
        alice.goto(BASE + "/notifications")
        project_note = alice.locator(".notif", has_text="liked your project")
        expect(project_note).to_be_visible(timeout=10000)
        expect(project_note.locator("a.snip")).to_have_attribute("href", "/projects/" + pid)

        bob.goto(BASE + "/collab")
        bob.get_by_role("button", name="New request").click()
        cmodal = bob.locator(".modal")
        cmodal.get_by_placeholder("e.g. Need a Go developer for a CLI").fill(f"Need a Rust reviewer {suffix}")
        cmodal.get_by_placeholder("go, cli, testing").fill("rust, testing")
        cmodal.get_by_role("button", name="Post request").click()
        expect(bob.locator(".proj-title.big")).to_contain_text("Need a Rust reviewer", timeout=10000)
        cid = re.search(r"/collab/(\d+)", bob.url).group(1)

        alice.goto(BASE + "/collab/" + cid)
        alice.get_by_placeholder("Say hi and what you'd bring (optional)").fill("I can help with the review.")
        alice.get_by_role("button", name="I'm interested").click()
        expect(alice.get_by_text("Status:")).to_be_visible(timeout=10000)
        bob.goto(BASE + "/collab/" + cid)
        expect(bob.get_by_text("Interested developers (1)")).to_be_visible(timeout=10000)
        bob.get_by_role("button", name="Accept").click()
        expect(bob.locator(".status-badge.accepted").first).to_be_visible(timeout=10000)
        alice.goto(BASE + "/notifications")
        expect(alice.locator(".notif", has_text="responded to your collaboration interest")).to_be_visible(timeout=10000)

        alice.goto(BASE + "/")
        alice.locator(".composer input[type=file]").set_input_files(pdf_path)
        expect(alice.locator(".composer .thumb-file", has_text="spec.pdf")).to_be_visible(timeout=15000)
        alice.locator(".composer textarea").first.fill("Spec attached for review")
        alice.locator(".compose-tools .btn.primary").click()
        spec_post = alice.locator("article.tweet", has_text="Spec attached for review").first
        chip = spec_post.locator("a.file-chip")
        expect(chip).to_contain_text("spec.pdf")
        expect(chip).to_have_attribute("download", "spec.pdf")
        with alice.expect_response(lambda r: "/media/" in r.url and r.status == 200):
            chip.evaluate("el => fetch(el.href).then(r => r.status)")

        spec_post.locator(".more").click()
        alice.get_by_text("Edit post", exact=True).click()
        alice.locator(".modal textarea").first.fill("Spec attached for review (updated)")
        alice.locator(".modal").get_by_role("button", name="Save", exact=True).click()
        expect(alice.locator("article.tweet", has_text="(updated)").first).to_contain_text("edited", timeout=10000)
        shot(alice, "09-projects-collab-files")

        print("15. mobile layout renders")
        mobile = alice_ctx.new_page()
        mobile.set_viewport_size({"width": 390, "height": 844})
        mobile.goto(BASE + "/")
        expect(mobile.locator(".sidebar")).to_be_visible()
        shot(mobile, "07-mobile")

        browser.close()

    if errors:
        print("JavaScript errors:")
        for e in errors:
            print("  ", e)
        sys.exit(1)
    print("ALL BROWSER CHECKS PASSED")


if __name__ == "__main__":
    main()
