#!/usr/bin/env python3
"""Crack the Hook: a game about Claude Code hooks.

    python3 play.py        (on Windows: py play.py)

Each level has a hook with a secret rule. You guess what it does, pick
its rule, find a command that gets past it, then fix it. The commands
never run: the game hands each one to the real hook the way Claude
Code would and shows you the answer. It uses no Claude credits.
"""

import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "levels.dat"
MY_HOOKS = Path(os.environ.get("HOOK_GAME_MY_HOOKS", str(HERE / "my-hooks")))

SCREEN = sys.stdout.isatty()
COLOR = SCREEN and os.name != "nt" and not os.environ.get("NO_COLOR")
WIDTH = 72
LINE = "=" * WIDTH

STOP_OR_PASS = {"s": "STOP", "stop": "STOP", "p": "PASS", "pass": "PASS"}
QUIT = {"q", "quit", "exit"}


class Quit(Exception):
    pass


def paint(text, code):
    return f"\033[{code}m{text}\033[0m" if COLOR else text


def red(text):
    return paint(text, "1;31")


def green(text):
    return paint(text, "1;32")


def bold(text):
    return paint(text, "1")


def verdict_word(verdict):
    return red("STOP") if verdict == "STOP" else green("PASS")


def say(text, indent=0):
    pad = " " * indent
    print(textwrap.fill(text, WIDTH, initial_indent=pad, subsequent_indent=pad))


def clear():
    if not SCREEN:
        print()
    elif os.name == "nt":
        os.system("cls")
    else:
        print("\033[2J\033[H", end="")


def read(prompt):
    try:
        answer = input(prompt)
    except EOFError:
        raise Quit
    answer = answer.strip().lower().strip("().")
    if answer in QUIT:
        raise Quit
    return answer


def ask(prompt, choices, help_line):
    """Ask until the answer is one of the choices. Returns its value."""
    while True:
        answer = read(prompt)
        if answer in choices:
            return choices[answer]
        print(help_line)


def pause(what):
    print()
    read(f"Press Enter to {what}. ")


class Game:
    def __init__(self):
        lines = DATA.read_text().splitlines()
        blob = "".join(line for line in lines if not line.startswith("#"))
        data = json.loads(zlib.decompress(base64.b64decode(blob)).decode())
        self.intro = data["intro"]
        self.finish = data["finish"]
        self.levels = data["levels"]
        self.hooks = data["hooks"]
        self.tmp = Path(tempfile.mkdtemp(prefix="crack-the-hook-"))
        for name, source in self.hooks.items():
            (self.tmp / name).write_text(source)
        for level in self.levels:
            world = self.tmp / f"world{level['number']}.json"
            world.write_text(json.dumps(level.get("world", {})))
        self.answers = {}

    def cleanup(self):
        shutil.rmtree(str(self.tmp), ignore_errors=True)

    # ---------- running a hook ----------

    def run_hook(self, level, hook_file, command):
        """Hand the command to a hook file exactly as Claude Code would.
        Returns ("STOP" or "PASS", None), or (None, error) if it crashed."""
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                   "tool_input": {"command": command}}
        world = self.tmp / f"world{level['number']}.json"
        env = dict(os.environ, HOOK_GAME_WORLD=str(world))
        try:
            proc = subprocess.run(
                [sys.executable, str(hook_file)], input=json.dumps(payload),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                universal_newlines=True, timeout=10, env=env)
        except subprocess.TimeoutExpired:
            return None, "The hook took more than 10 seconds and was stopped."
        except (OSError, subprocess.SubprocessError) as error:
            return None, str(error)
        if proc.returncode == 2:
            return "STOP", None
        if proc.returncode == 0:
            return "PASS", None
        return None, proc.stderr.strip() or f"The hook exited with code {proc.returncode}."

    def hook_says(self, level, command):
        """What the level's own hook says about a command."""
        number = level["number"]
        if (number, command) not in self.answers:
            verdict, _ = self.run_hook(level, self.tmp / f"level{number}.py", command)
            # Claude Code runs the command if a hook crashes.
            self.answers[(number, command)] = verdict or "PASS"
        return self.answers[(number, command)]

    # ---------- screen pieces ----------

    def header(self, level, part, setup=True):
        clear()
        print(bold(LINE))
        print(bold(f"LEVEL {level['number']} of {len(self.levels)}    {part}"))
        print(bold(LINE))
        print()
        if setup:
            for line in level["setup"]:
                print(line)
            print()

    def show_board(self, board):
        print("What the hook did so far:")
        for wanted in ("STOP", "PASS"):
            for command, verdict in board:
                if verdict == wanted:
                    print(f"  {verdict_word(verdict)}  {command}")
        print()

    def pick(self, options, show):
        """Let the player pick an option until they get the right one.
        Returns 1 if they got it on the first try, else 0."""
        letters = "abc"[:len(options)]
        for letter, option in zip(letters, options):
            print(f"  {letter})  {show(option)}")
        print()
        prompt = f"Type {', '.join(letters[:-1])}, or {letters[-1]}: "
        help_line = f"  Type one letter: {', '.join(letters[:-1])}, or {letters[-1]}."
        choices = {letter: i for i, letter in enumerate(letters)}
        first_try = True
        while True:
            option = options[ask(prompt, choices, help_line)]
            print()
            if option["right"]:
                print(green("  Yes!"))
                say(option["why"], 2)
                return 1 if first_try else 0
            print("  Not that one.")
            say(option["why"] + " Try again.", 2)
            print()
            first_try = False

    # ---------- parts 1 to 3 ----------

    def play_level(self, level):
        cards = [command for command, _ in level["cards"]]
        board = [(command, self.hook_says(level, command))
                 for command, _ in level["examples"]]
        score = 0

        self.header(level, "Getting started")
        print("Here's what the hook did with two commands:")
        for command, verdict in board:
            print(f"  {verdict_word(verdict)}  {command}")
        print()
        say(f"In part 1, you'll guess what it does with {len(cards)} more "
            "commands. After each guess, you'll see what it really did.")
        pause("start part 1")

        for i, command in enumerate(cards, 1):
            self.header(level, f"Part 1 of 4: Guess    (command {i} of {len(cards)})")
            self.show_board(board)
            print("Next command:")
            print()
            print("    " + bold(command))
            print()
            guess = ask("Will the hook STOP it or let it PASS? Type s or p: ",
                        STOP_OR_PASS, "  Type s for STOP or p for PASS.")
            verdict = self.hook_says(level, command)
            print()
            if guess == verdict:
                score += 1
                print(green("  Right!") + f" The hook said {verdict_word(verdict)}.")
            else:
                print(f"  Not this time. The hook said {verdict_word(verdict)}.")
            board.append((command, verdict))
            pause("see the next command" if i < len(cards) else "go to part 2")

        self.header(level, "Part 2 of 4: Pick the rule")
        self.show_board(board)
        print("Which rule is the hook following?")
        print()
        score += self.pick(level["rule"], lambda option: option["text"])
        pause("go to part 3")

        self.header(level, "Part 3 of 4: Get past the hook")
        say(level["leak_intro"])
        print()
        say(level["leak_question"])
        print()
        score += self.pick(level["leak"], lambda option: option["command"])
        pause("look inside the hook")

        self.header(level, "Inside the hook", setup=False)
        print("Here's the check inside the hook. It's written in Python.")
        print()
        for line in textwrap.dedent(level["code"]).splitlines():
            print("    " + line)
        print()
        say(level["plain"])
        print()
        say(level["takeaway"])
        pause("go to part 4")

        score += self.part4(level)
        possible = len(cards) + 3
        print()
        print(bold(f"Level {level['number']} score: {score} of {possible} points."))
        return score, possible

    # ---------- part 4 ----------

    def part4(self, level):
        """Fix the hook (or, on a level that can't be fixed by matching
        words, answer a question about why). Returns the points earned."""
        fix = level["fix"]
        if "question" in fix:
            self.header(level, "Part 4 of 4: " + fix["title"], setup=False)
            say(fix["intro"])
            print()
            say(fix["question"])
            print()
            got = self.pick(fix["options"], lambda option: option["text"])
            print()
            say(fix["takeaway"])
            return got

        path = MY_HOOKS / f"level{level['number']}.py"
        note = None
        if path.exists():
            note = "This is your copy from last time. Type r to start over with a fresh one."
        else:
            self.fresh_copy(level, path)
        results = None
        while True:
            self.fix_screen(level, path, note, results)
            note = None
            answer = read("Press Enter to test your hook (s to skip, r to start over): ")
            if answer in ("s", "skip"):
                print()
                print("  Skipped. Your copy stays in the my-hooks folder.")
                return 0
            if answer in ("r", "reset") or not path.exists():
                self.fresh_copy(level, path)
                note = "The game saved a fresh copy of the hook. Open it again."
                results = None
                continue
            results = self.test_fix(level, path)
            if results["fixed"]:
                self.fix_screen(level, path, None, results)
                return 1

    def fresh_copy(self, level, path):
        """Save a copy of the level's hook, with a FIX ME comment above
        the line that decides."""
        fix = level["fix"]
        lines = self.hooks[f"level{level['number']}.py"].splitlines()
        at = lines.index(fix["marker"])
        lines.insert(at, fix["comment"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n")

    def checklist(self, level):
        """Every command the player saw in this level, with the answer a
        fixed hook should give."""
        fix = level["fix"]
        seen = list(level["examples"]) + list(level["cards"])
        seen += [(option["command"], option["verdict"]) for option in level["leak"]]
        wanted = {}
        for command, verdict in seen:
            wanted[command] = "STOP" if command == fix["flip"] else verdict
        return wanted

    def test_fix(self, level, path):
        rows = []
        for command, want in self.checklist(level).items():
            got, error = self.run_hook(level, path, command)
            if error:
                return {"fixed": False, "error": error, "rows": []}
            rows.append((command, want, got))
        fixed = all(want == got for _, want, got in rows)
        return {"fixed": fixed, "error": None, "rows": rows}

    def fix_screen(self, level, path, note, results):
        fix = level["fix"]
        self.header(level, "Part 4 of 4: " + fix["title"], setup=False)
        say(fix["task"])
        print()
        print("    " + bold(fix["flip"]))
        print()
        say("Change the hook so this command gets a STOP. Every other command "
            "should still get the same answer as before.")
        print()
        print("The game saved a copy of the hook in the my-hooks folder, next to")
        print("play.py. Open it in your code editor:")
        print()
        print("    " + str(path))
        print()
        say(fix["hint"])
        print()
        if note:
            say(note)
            print()
        if not results:
            say("Change the file and save it. Then come back here and test it.")
            print()
            return
        if results["error"]:
            print(red("Your hook crashed, so it couldn't answer."))
            say("In Claude Code, a crashed hook lets every command through. Here's "
                "the end of the error Python gave:")
            print()
            for line in results["error"].splitlines()[-6:]:
                print("    " + line)
            print()
            say("Fix the error and save the file. Then test it again.")
            print()
            return
        print("Your hook's answers:")
        for wanted in ("STOP", "PASS"):
            print(f"  Should {wanted}:")
            for command, want, got in results["rows"]:
                if want == wanted:
                    mark = green("ok   ") if got == want else red("WRONG")
                    print(f"    {mark}  {command}")
        print()
        if results["fixed"]:
            print(green("Yes! You fixed it."))
            say(fix["done"])
        else:
            wrong = sum(1 for _, want, got in results["rows"] if want != got)
            still = "1 command is" if wrong == 1 else f"{wrong} commands are"
            say(f"{still} still wrong. Change the file, save it, then test it again.")
        print()

    # ---------- the whole game ----------

    def run(self):
        clear()
        print(bold("CRACK THE HOOK"))
        print()
        print(self.intro)
        print()
        last = len(self.levels)
        numbers = [str(n) for n in range(1, last + 1)]
        print(f"To jump to a level, type {' or '.join(numbers[1:])}. To go straight "
              "to part 4 of a level, type f.")
        choices = {n: int(n) for n in numbers}
        choices[""] = 1
        choices["f"] = "f"
        start = ask("Press Enter to start level 1: ", choices,
                    f"  Press Enter, type {' or '.join(numbers[1:])}, or type f.")

        if start == "f":
            number = ask(f"Part 4 of which level? Type {', '.join(numbers[:-1])}, "
                         f"or {numbers[-1]}: ", {n: int(n) for n in numbers},
                         f"  Type {', '.join(numbers[:-1])}, or {numbers[-1]}.")
            level = self.levels[number - 1]
            got = self.part4(level)
            print()
            print(bold(f"Part 4 score: {got} of 1 point."))
            pause("finish")
            clear()
            say("Run play.py again to play another level or fix another hook.")
            return

        total = possible = 0
        for level in self.levels[start - 1:]:
            got, out_of = self.play_level(level)
            total += got
            possible += out_of
            if level["number"] < last:
                pause(f"start level {level['number'] + 1}")
            else:
                pause("finish")

        clear()
        print(bold("CRACK THE HOOK"))
        print()
        print(bold(f"You finished! You got {total} of {possible} points."))
        print()
        say(self.finish)
        print()


def main():
    if not DATA.exists():
        print("Can't find levels.dat. Keep it in the same folder as play.py.")
        return 1
    game = Game()
    try:
        game.run()
    except (Quit, KeyboardInterrupt):
        print("\n\nBye! Run play.py again to play. You can jump to any level.")
    finally:
        game.cleanup()
    return 0


if __name__ == "__main__":
    sys.exit(main())
