#!/usr/bin/env python3
import subprocess, re, sys, textwrap

# ANSI styles
BOLD      = '\033[1m'
BLUE      = '\033[94m'
RESET     = '\033[0m'
HIGHLIGHT = '\033[44;97m'   # white text on blue background
WIDTH     = 80
PAGE_SIZE = 20

STOPWORDS = {
    'i','need','to','my','something','the','a','an','and','or','for',
    'in','of','on','with','pc','you','show','list'
}

def run_cmd(cmd, shell=False):
    try:
        return subprocess.check_output(cmd,
                                       stderr=subprocess.DEVNULL,
                                       shell=shell).decode()
    except subprocess.CalledProcessError:
        return ""

def search_commands(term):
    out = run_cmd(['apropos', term])
    res = []
    for line in out.splitlines():
        parts = line.split(' - ', 1)
        if len(parts) == 2:
            res.append((parts[0].split()[0], parts[1]))
    return res

def intersect_search(phrase):
    words = re.findall(r'\w+', phrase.lower())
    kws   = [w for w in words if w not in STOPWORDS and len(w) > 2]
    if not kws:
        what = run_cmd(['whatis', phrase])
        for line in what.splitlines():
            if line.lower().startswith(phrase.lower()):
                name, desc = line.split(' - ', 1)
                return ([(name.strip(), desc.strip())], [phrase])
        matches = search_commands(phrase)
        return (matches, [phrase]) if matches else ([], [])
    sets = []
    for kw in kws:
        s = {c for c, _ in search_commands(kw)}
        if not s:
            return [], kws
        sets.append(s)
    common = set.intersection(*sets)
    if not common:
        return [], kws
    mapping = {}
    for kw in kws:
        for c, d in search_commands(kw):
            if c in common and c not in mapping:
                mapping[c] = d
    matches = sorted([(c, mapping[c]) for c in common], key=lambda x: x[0])
    return matches, kws

def union_search(phrase):
    words = re.findall(r'\w+', phrase.lower())
    kws   = [w for w in words if w not in STOPWORDS and len(w) > 2]
    if not kws:
        matches = search_commands(phrase)
        return (matches, [phrase]) if matches else ([], [])
    seen, raw = set(), []
    for kw in kws:
        for c, d in search_commands(kw):
            if c not in seen:
                seen.add(c)
                raw.append((c, d))
    scored = []
    for c, d in raw:
        score = sum(c.lower().count(kw) + d.lower().count(kw) for kw in kws)
        scored.append((c, d, score))
    scored.sort(key=lambda x: (-x[2], x[0]))
    return [(c, d) for c, d, _ in scored], kws

def highlight(text, kws):
    for kw in kws:
        pat = re.compile(re.escape(kw), re.IGNORECASE)
        text = pat.sub(lambda m: f"{HIGHLIGHT}{m.group(0)}{RESET}", text)
    return text

def paginate_list(items, kws):
    total, page = len(items), 0
    while True:
        s = page * PAGE_SIZE
        e = min(s + PAGE_SIZE, total)
        print(f"\n{BOLD}Matching commands {s+1}-{e} of {total}:{RESET}")
        for i in range(s, e):
            c, d = items[i]
            d_h = highlight(d, kws)
            if d_h != d:
                c_h = f"{HIGHLIGHT}{c}{RESET}"
            else:
                c_h = highlight(c, kws)
            print(f"  {i+1}. {c_h} — {d_h}")
        choice = input("Enter number, 'n' next, 'p' prev, 'q' new search, 'x' exit: ").strip().lower()
        if choice.isdigit():
            n = int(choice)
            if 1 <= n <= total:
                return items[n-1][0]
            print("Number out of range.")
        elif choice == 'n':
            if e < total:
                page += 1
            else:
                print("no more options")
        elif choice == 'p':
            if s > 0:
                page -= 1
            else:
                print("no more options")
        elif choice == 'q':
            return 'NEW_SEARCH'
        elif choice == 'x':
            sys.exit(0)
        else:
            print("Invalid input.")

def get_man(cmd):
    return run_cmd(f"man {cmd} | col -b", shell=True)

def split_sections(text):
    secs, cur, buf = {}, None, []
    for line in text.splitlines():
        if re.match(r'^[A-Z][A-Z0-9 _-]+$', line.strip()):
            if cur:
                secs[cur] = "\n".join(buf).strip()
            cur, buf = line.strip(), []
        elif cur:
            buf.append(line)
    if cur:
        secs[cur] = "\n".join(buf).strip()
    return secs

def extract_opts_fallback(raw):
    # match options starting at column 0 or indented continuation lines
    pat = r'(?m)^(?:\s*-\S.*(?:\n[ \t]+.*)*)'
    return "\n".join(re.findall(pat, raw)).strip()

def list_flags(opts):
    return sorted(set(re.findall(r'(?m)^ {1,}(-\S+)', opts)))

def print_header(name):
    print("\n\n" + f"{BOLD}{BLUE}=== {name} ==={RESET}\n")

def print_section(name, body):
    print_header(name)
    for p in body.split('\n\n'):
        print(textwrap.fill(p, WIDTH, subsequent_indent='  '))
    print()

def print_options(body):
    print_header('OPTIONS')
    for l in body.splitlines():
        print(textwrap.fill(l.strip(),
                              WIDTH,
                              initial_indent='  ',
                              subsequent_indent='      '))
    print()

def display_menu():
    print(f"\n{BOLD}What would you like to view?{RESET}")
    for num, label in [
        ('1','Show ALL'),
        ('2','Show OPTIONS'),
        ('3','Show SYNOPSIS'),
        ('4','SYNOPSIS + OPTIONS'),
        ('5','Show EXAMPLES'),
        ('6','SYNOPSIS + OPTIONS + EXAMPLES'),
        ('7','Show a SPECIFIC OPTION'),
        ('8','Change command'),
        ('9','Exit')
    ]:
        print(f"  {num}. {label}")
    return input("Choice: ").strip()

def choose_and_display(raw, secs):
    ch = display_menu()
    if ch == '1':
        print(raw)
    elif ch in ('2','3','4','5','6'):
        mapping = {
            '2':['OPTIONS'],
            '3':['SYNOPSIS'],
            '4':['SYNOPSIS','OPTIONS'],
            '5':['EXAMPLES'],
            '6':['SYNOPSIS','OPTIONS','EXAMPLES']
        }
        for sec in mapping[ch]:
            body = secs.get(sec, '').strip()
            if sec == 'OPTIONS' and not body:
                body = extract_opts_fallback(raw)
            if sec == 'OPTIONS':
                print_options(body if body else "(none)")
            elif sec == 'EXAMPLES':
                print_header(sec)
                if body:
                    print(textwrap.fill(body, WIDTH, subsequent_indent='  '))
                else:
                    print("  there are no examples for this command\n")
            else:
                print_section(sec, body if body else "(none)")
    elif ch == '7':
        opts = secs.get('OPTIONS','').strip() or extract_opts_fallback(raw)
        flags = list_flags(opts)
        if not flags:
            print("No options found.")
        else:
            print_header('SPECIFIC OPTION')
            for i, f in enumerate(flags, 1):
                print(f"  {i}. {f}")
            sel = input("Select option #: ").strip()
            if sel.isdigit() and 1 <= int(sel) <= len(flags):
                flag = flags[int(sel)-1]
                pat = rf'(?m)(^\s{{1,}}{re.escape(flag)}.*(?:\n\s{{2,}}.*)*)'
                m = re.search(pat, opts)
                desc = m.group(1).strip() if m else "No description."
                print_section(flag, desc)
                ex = secs.get('EXAMPLES', "").strip()
                print_header('EXAMPLES')
                if ex:
                    print(textwrap.fill(ex, WIDTH, subsequent_indent='  '))
                else:
                    print("  there are no examples for this command\n")
            else:
                print("Invalid selection.")
    elif ch == '8':
        return 'NEW_SEARCH'
    elif ch == '9':
        sys.exit(0)
    else:
        print("Invalid choice.")
    return None

def main():
    while True:
        print(f"\n{BOLD}1){RESET} i need info about a command")
        print(f"{BOLD}2){RESET} Find command by keyword")
        print(f"{BOLD}3){RESET} Exit")
        raw_choice = input("Choice: ").strip()
        if raw_choice == '3':
            sys.exit(0)

        if raw_choice in ('1','2'):
            mode = raw_choice
            prompt = "Describe what you need: " if mode == '1' else "Enter search term (apropos): "
            phrase = input(prompt).strip()
        else:
            mode = '2'
            phrase = raw_choice

        # replace "folder" → "directory", then "directory" → "directories"
        phrase = re.sub(r'(?i)\bfolder\b', 'directory', phrase)
        phrase = re.sub(r'(?i)\bdirectory\b', 'directories', phrase)

        if mode == '1':
            matches, kws = intersect_search(phrase)
        else:
            matches, kws = union_search(phrase)

        if not matches:
            print("No commands found; try again.")
            continue

        cmd = paginate_list(matches, kws)
        if cmd == 'NEW_SEARCH':
            continue

        while True:
            raw  = get_man(cmd)
            secs = split_sections(raw)
            action = choose_and_display(raw, secs)
            if action == 'NEW_SEARCH':
                break

if __name__ == '__main__':
    main()
