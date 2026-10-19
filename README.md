# Crack the Hook

A game about Claude Code hooks, for the AI301 unit 6 activity. Each level has a hook with a secret rule. You guess what the hook does, pick its rule, find a command that gets past it, and then fix the hook.

The commands in the game never really run, and the game uses no Claude credits.

## Get the game

```
git clone https://github.com/smoran02/ai301-unit6-crack-the-hook.git
cd ai301-unit6-crack-the-hook
```

Or click **Code**, then **Download ZIP** on this page, and unzip it.

## Play

```
python3 play.py
```

On Windows, type `py play.py` instead. You need Python 3.8 or newer and nothing else.

In parts 1 to 3, you type one letter and press Enter. In part 4, the game saves a copy of the hook in the `my-hooks` folder, and you fix it in your code editor. To go straight to part 4 of a level, type `f` on the first screen. Type `q` any time to quit.

## One rule

Don't open `levels.dat`. The answers are in it.
