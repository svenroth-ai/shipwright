# Visual guidelines

Source: REA (read from the `:root` block and the component CSS of the real board, `templates/board.html` of the social-engagement skill; svenroth.ai design system, tokens.json v2).

Warm and calm: a beige page, off-white cards, one teal accent, rust only for warnings, open feedback and skipped or expired threads. Inter for text, Geist Mono for small labels, eyebrows, dates, counts and status chips (upper case, wide letter spacing). The thread on the right looks like the platform it came from (Reddit, Hacker News, LinkedIn, X) inside a brand card; everything around it is the brand. Look and structure come from the Untitled UI design kit (tabs "button white border", secondary and primary buttons, popover, dropdown listbox); this file supplies the brand tokens as `--name: value` lines so the kit can read them.

## Colours
- --color-bg: #eceae4
- --color-surface: #fbfaf7
- --color-table-header: #f4f2ec
- --color-text: #15141a
- --color-muted: #45433d
- --color-border: #e2ded6
- --color-border-strong: #7a7568
- --color-primary: #0b7160
- --color-primary-hover: #095e50
- --color-primary-soft: #cfe6df
- --color-on-primary: #ffffff
- --color-hover: #f1efe9
- --color-focus: #15141a
- --color-primary-ring: #cfe6df
- --color-secondary: #128a76

## Status colours
- --color-success: #0b7160
- --color-success-bg: #e3f0e6
- --color-warning: #8a3c12
- --color-warning-bg: #f6e8d6
- --color-error: #a63d18
- --color-error-bg: #f8e4dc
- --color-info: #1d4e89
- --color-info-bg: #e6eef6

## Typography
- --font-family: Inter
- --font-mono: Geist Mono
- --font-size-base: 16px
- --font-size-sm: 14px
- --font-size-lg: 18px

Headings: board title 22px/700, letter spacing -0.4px; thread title 18px/700; summary terms 14px/700. Eyebrows: Geist Mono 12 to 13px, 500, letter spacing 2px, upper case, colour primary. Body letter spacing -0.01em.

## Spacing and shape
- 4px base unit; top bar padding 20px 32px; list rows 10px 12px with 4px gap; main column padding 24px 32px; card padding 18px 20px (thread) and 0 24px 20px (summary)
- radius 8px for controls and list rows, 14px for cards, 999px for chips and counts
- card shadow: `0 2px 4px rgba(20,20,15,0.04), 0 16px 34px -20px rgba(20,20,15,0.13)`
- layout: list column 300px (drag 200 to 480px, kept per browser), content max 1000px, page max 1280px; below 820px the list is hidden and a picker shows above the thread

## Components (as the real board draws them)
- Platform switch: tinted track (`#e4e1d8`), selected tab white and raised, count pill per tab (teal-soft when selected).
- Status filter: secondary button with a funnel icon, label and count, opening a listbox (Open, Posted, Skipped, Expired, All, each with a count and a tick).
- List row: eyebrow line (where, date), title clamped to two lines, meta line (comments, age) with dots: rust "N feedback", teal-soft status, accent "new"/"updated".
- Action bar (sticky): date, keyword, position "n of m", status chip, Open thread, Skip, Mark posted (primary; opens a popover with the comment link) or Reopen.
- Summary card: 2px accent border, teal-soft eyebrow band, Question / Others say / Our angle (angle bold), then the feedback field, Save, the feedback history (chips open rust, applied teal, declined grey) and "Jump to the draft".
- Draft card: 2px accent border on surface, eyebrow "Draft reply" (+ "updated"), the text, Copy reply (primary), Open thread, and a second Mark posted row with the link field; X adds "n/280" (red when over).
- Reload toast: dark pill at the bottom centre, "Claude updated the board", Reload.

## Platform skins (inside the thread card only)
- Reddit: IBM Plex Sans/Arial, subreddit in `#c33a00` bold, light comment rail `#edeff1`.
- Hacker News: background `#f6f6ef`, Verdana 13px, orange bar `#ff6600`, grey meta `#5f5f5f`, indented comments without rail.
- LinkedIn: system UI font, round grey avatar, comments in `#f3f2ef` bubbles indented 50px.
- X: Segoe UI, round avatar, rail `#cfd9de`, count text `#536471`, over-limit `#d4202c`.

## Real board tokens (reference, values as shipped)
`--bg:#eceae4; --bg-alt:#f4f2ec; --card:#fbfaf7; --cream:#f1efe9; --pill:#e5e2da; --sand:#e4e1d8; --line:#e2ded6; --border-strong:#cdc7ba; --ink:#15141a; --text-lead:#45433d; --muted:#6c6a64; --accent:#128a76; --accent-deep:#0c8470; --teal-deep:#0b7160; --teal-soft:#cfe6df; --rust:#a63d18; --radius-sm:8px; --radius-md:14px`; body 15px/1.55, small text 13px.

Mapping to the kit names above: bg=bg, surface=card, table-header=bg-alt, text=ink, muted=text-lead, border=line, primary=teal-deep, primary-hover=the real `.btn-primary:hover` value, primary-soft=teal-soft, secondary=accent, error=rust, hover=cream, focus=ink (the real `:focus-visible` outline). Three values differ from the real board on purpose, because the kit's contrast and size rules require it (see OPEN.md): `--color-muted` uses text-lead instead of the real `--muted` #6c6a64 (4.5:1 on bg, the kit wants 7:1 for secondary text), `--color-border-strong` is #7a7568 instead of the hairline #cdc7ba (1.6:1 on surface, controls need 3:1), and the font sizes are 16/14px instead of 15/13px. Warning, info and the status backgrounds have no counterpart on the real board and are invented in the same warm range.
