# -*- coding: utf-8 -*-
"""맥 러너 진단 — 렉·검은 줄 제보를 숫자로 가른다 (CI 전용).

    python3 diag_mac.py <parts_폴더>

실기기가 없으므로 GitHub Actions 맥 러너에서 실제 Mascot 을 띄워 잰다:
  1) 생성(첫 창까지) 시간 — '켜지지도 않는다' 제보의 후보
  2) 프레임(_tick_body) 시간 분포 + _safe 구역별 누적 시간 — 렉의 범인
  3) NSWindow 를 주기적으로 열거해 **자라는 창**을 색출 — '까만 두 줄이
     계속 커진다' 제보의 정체 (창인가, 캔버스 안 그림인가)
  4) 소품을 만두·고양이로 강제해 각각 잰다 (최근에 넣은 모션이 범인인지)
  5) 끝나면 .error.log 와 맥 로그를 통째로 쏟는다

지뢰 51: '안 보인다'류는 화면만 보고 못 가른다 — 숫자를 남긴다.
"""
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
CHAR = ARGS[0] if ARGS else "parts_saga"
ONLY_BGM = "--bgm" in sys.argv      # 플레이리스트 단계만 (빨리 끝내려고)


class _Skip(Exception):
    """--bgm 일 때 옛 단계를 건너뛴다."""

t_imp0 = time.time()
import mascot as M                                    # noqa: E402
print("[진단] import mascot: %.2fs" % (time.time() - t_imp0), flush=True)

M.Mascot._room_tick = lambda self, now: None          # 서버는 안 건드린다


# ── _safe 구역별 시간 + 프레임 시간 계측 ────────────────────────────
acc = {}
frames = []
orig_safe = M.Mascot._safe


def safe_timed(self, name, fn, *a, **k):
    t0 = time.perf_counter()
    try:
        return orig_safe(self, name, fn, *a, **k)
    finally:
        dt = time.perf_counter() - t0
        s = acc.setdefault(name, [0.0, 0, 0.0])
        s[0] += dt
        s[1] += 1
        s[2] = max(s[2], dt)


orig_body = M.Mascot._tick_body


def body_timed(self):
    t0 = time.perf_counter()
    try:
        return orig_body(self)
    finally:
        frames.append(time.perf_counter() - t0)


M.Mascot._safe = safe_timed
M.Mascot._tick_body = body_timed


def dump_stats(tag):
    if frames:
        fs = sorted(frames)
        n = len(fs)
        print("[진단:%s] 프레임 %d개 · 중앙 %.1fms · 상위90%% %.1fms · 최대 %.1fms"
              % (tag, n, fs[n // 2] * 1000, fs[int(n * 0.9)] * 1000,
                 fs[-1] * 1000), flush=True)
    top = sorted(acc.items(), key=lambda kv: -kv[1][0])[:14]
    for name, (tot, cnt, mx) in top:
        print("   %-18s 합 %7.1fms · %5d번 · 최대 %6.1fms"
              % (name, tot * 1000, cnt, mx * 1000), flush=True)
    frames.clear()
    acc.clear()


def dump_windows(tag, prev):
    """NSWindow 열거 — 자라는 창을 색출한다."""
    try:
        from AppKit import NSApplication
        wins = NSApplication.sharedApplication().windows()
        cur = {}
        for w in wins:
            try:
                f = w.frame()
                key = "%s#%d" % (w.className(), w.windowNumber())
                cur[key] = (int(f.size.width), int(f.size.height),
                            int(f.origin.x), int(f.origin.y),
                            bool(w.isVisible()))
            except Exception:
                pass
        for key, v in sorted(cur.items()):
            old = prev.get(key)
            grow = ""
            if old and (v[0] > old[0] or v[1] > old[1]):
                grow = "  ← 커졌다! %sx%s → %sx%s" % (old[0], old[1], v[0], v[1])
            if old != v or grow:
                print("[창:%s] %-28s %4dx%-4d at(%d,%d) 보임=%s%s"
                      % (tag, key, v[0], v[1], v[2], v[3], v[4], grow),
                      flush=True)
        return cur
    except Exception as e:
        print("[창] 열거 실패 %r" % e, flush=True)
        return prev


def run_phase(m, tag, secs, prev_wins, probe=None):
    t_end = time.time() + secs
    last_win = time.time()
    c0, w0 = time.process_time(), time.time()
    while time.time() < t_end:
        try:
            m.root.update()
        except Exception as e:
            print("[진단:%s] update 예외 %r" % (tag, e), flush=True)
            break
        if probe is not None:
            try:
                probe()
            except Exception:
                pass
        time.sleep(0.01)
        if time.time() - last_win > 3.0:
            last_win = time.time()
            prev_wins = dump_windows(tag, prev_wins)
    c1, w1 = time.process_time(), time.time()
    # CPU 점유 — 'CPU 를 많이 잡아먹는다' 제보를 숫자로 (퀸시). 이 루프의
    # update()+sleep(0.01) 몫이 섞이므로 절대값보다 **단계끼리의 차이**를 본다.
    print("[진단:%s] CPU %.0f%% (process_time %.2fs / %.2fs)"
          % (tag, 100.0 * (c1 - c0) / max(1e-6, w1 - w0), c1 - c0, w1 - w0),
          flush=True)
    dump_stats(tag)
    return prev_wins


SHOTS = os.path.join(HERE, "shots")


def grab_window(win, name):
    """그 Tk 창 하나만 PNG 로 (자기 창은 러너에서도 된다 · 지뢰 139)."""
    try:
        os.makedirs(SHOTS, exist_ok=True)
        import Quartz
        from Quartz import (CGWindowListCopyWindowInfo, CGRectNull,
                            kCGWindowListOptionOnScreenOnly, kCGNullWindowID,
                            CGImageDestinationCreateWithURL,
                            CGImageDestinationAddImage,
                            CGImageDestinationFinalize)
        from Foundation import NSURL
        win.update_idletasks()
        ww, wh = win.winfo_width(), win.winfo_height()
        infos = CGWindowListCopyWindowInfo(
            kCGWindowListOptionOnScreenOnly, kCGNullWindowID) or []
        pid = os.getpid()
        best = None
        for it in infos:
            if int(it.get("kCGWindowOwnerPID", -1)) != pid:
                continue
            b = it.get("kCGWindowBounds") or {}
            if abs(b.get("Width", 0) - ww) < 40 and \
                    abs(b.get("Height", 0) - wh) < 80:
                best = int(it["kCGWindowNumber"])
        if best is None:
            print("[찍기] %s — 창 번호 못 찾음 (%dx%d)" % (name, ww, wh),
                  flush=True)
            return
        img = Quartz.CGWindowListCreateImage(
            CGRectNull, Quartz.kCGWindowListOptionIncludingWindow, best,
            Quartz.kCGWindowImageBoundsIgnoreFraming)
        if img is None:
            print("[찍기] %s — 캡처 실패" % name, flush=True)
            return
        path = os.path.join(SHOTS, name + ".png")
        dest = CGImageDestinationCreateWithURL(
            NSURL.fileURLWithPath_(path), "public.png", 1, None)
        CGImageDestinationAddImage(dest, img, None)
        okd = CGImageDestinationFinalize(dest)
        print("[찍기] %s %dx%d → %s" % (name, Quartz.CGImageGetWidth(img),
                                       Quartz.CGImageGetHeight(img),
                                       "성공" if okd else "실패"), flush=True)
    except Exception as e:
        print("[찍기] %s 실패 %r" % (name, e), flush=True)


def team_setup(m):
    """같이하기 상태를 흉내 낸다 — 방장 + 참가자 셋, 집중 구간 (서버 없이)."""
    class Net:
        calls = 0
        stat = {}
        err = None
        idle = False
        key = b"k"

        def __init__(self):
            self.ok_at = self.born = time.time()

        def push(self, *a, **k): pass
        def send(self, *a, **k): return True
        def drain(self): return [], []
        def take_sent(self): return []
        def stop(self): pass

    m.room_net = Net()
    m._team_bcast = lambda *a, **k: None
    m._team_send = lambda *a, **k: None
    m.us["show_timer"] = True
    m.timer_on = True
    m._team_gate = lambda: True             # 같이하기 켜짐 (설정과 무관하게)
    m._team_new("norm", "오늘은 배경까지")
    sid = m._tm["sid"]
    m._tm["state"] = "run"
    peers = [s for s in m.ROOM_SEATS if s != m.char][:3]
    for sl in peers:
        m._tm["members"][sl] = {"v": "라인 마무리", "at": time.time()}
    m.room_people = [{"slot": s, "s": "work", "n": s, "lv": 3, "t": 30,
                      "p": 0.3, "tm": {"i": sid, "h": m.char,
                                       "v": "라인 마무리", "f": 0.5, "w": 1}}
                     for s in peers]
    st = m._pomo()
    st.update({"on": True, "phase": "focus", "end": time.time() + 900})
    m._pomo_save(st)


print("[진단] Mascot 생성 시작 (%s)" % CHAR, flush=True)
t0 = time.time()
try:
    m = M.Mascot(char_dir=CHAR)
except SystemExit as e:
    print("[진단] SystemExit %r — 중복 방지?" % e, flush=True)
    raise
print("[진단] 생성까지 %.2fs · 매끈=%s" % (time.time() - t0,
                                       getattr(m, "_smooth_on", "?")),
      flush=True)
m.root.update()
m.can_talk = True

wins = dump_windows("시작", {})
if not ONLY_BGM:
    wins = run_phase(m, "기본소품", 18, wins)

# ── 같이하기 (퀸시 'CPU 많이 먹음' 제보) — 띠·커서 곁·창 열림을 각각 잰다 ──
try:
    if ONLY_BGM:
        raise _Skip()
    team_setup(m)
    print("[진단] 같이하기 흉내 — 멤버 %d · 띠 켜짐=%s"
          % (len(m._tm["members"]), m.us.get("pomo_strip", True)), flush=True)
    wins = run_phase(m, "같이·띠·가만히", 14, wins)
    st9 = getattr(m, "_strip", None)
    print("[진단] 띠 창 모드=%s 보임=%s 그림=%s" % (
        getattr(st9, "mode", None), getattr(st9, "visible", None),
        (m._strip_im.size if m._strip_im is not None else None)), flush=True)
    # ── 띠가 왜 안 보이나 (사가 제보) — 문마다 답을 남긴다 ──────────
    try:
        pw9 = getattr(m, "_pomo_winref", None)
        pst9 = None
        try:
            pst9 = (pw9.state() if (pw9 is not None and pw9.winfo_exists())
                    else "없음")
        except Exception as e9:
            pst9 = "물음실패 %r" % e9
        print("[띠] want=%s · 사람 %d명 · tm=%s · gate=%s · 설정=%s · "
              "fs_hidden=%s · chip_hide=%s · 뽀모창=%s"
              % (m._strip_want(), len(m._strip_people()), bool(m._tm),
                 m._team_gate(), m.us.get("pomo_strip", True),
                 getattr(m, "_fs_hidden", None),
                 getattr(m, "_chip_hide", None), pst9), flush=True)
        print("[띠] 사람들=%s" % ([p[0] for p in m._strip_people()],),
              flush=True)
        if st9 is not None:
            t9 = st9.top
            print("[띠] 창 %dx%d at(%d,%d) 보임=%s _shown=%s"
                  % (t9.winfo_width(), t9.winfo_height(), t9.winfo_rootx(),
                     t9.winfo_rooty(), bool(t9.winfo_ismapped()),
                     getattr(st9, "_shown", None)), flush=True)
            # 색상키 필터가 이 창에 걸렸나 (안 걸리면 검은 상자 · 지뢰 126)
            try:
                from AppKit import NSApplication
                ck9 = getattr(m, "_mac_ck", None)
                want9 = getattr(ck9, "filter", None)
                for w9 in NSApplication.sharedApplication().windows():
                    f9 = w9.frame()
                    if abs(int(f9.size.width) - t9.winfo_width()) > 4:
                        continue
                    cv0 = w9.contentView()
                    lay9 = cv0.layer() if cv0 else None
                    filt9 = lay9.compositingFilter() if lay9 is not None                         else None
                    print("[띠] NSWindow style=%d 보임=%s 필터=%s 알파=%s"
                          % (int(w9.styleMask()), bool(w9.isVisible()),
                             "걸림" if (filt9 == want9 if want9 is not None
                                       else bool(filt9)) else "없음",
                             w9.alphaValue()), flush=True)
            except Exception as e9:
                print("[띠] NSWindow 훑기 실패 %r" % e9, flush=True)
            grab_window(t9, "strip")
    except Exception as e9:
        import traceback
        print("[띠] 진단 실패 %r" % e9, flush=True)
        traceback.print_exc()
    m._cur_near = True                       # 커서가 곁 → 60fps 경로
    wins = run_phase(m, "같이·띠·커서곁", 14, wins)
    m._cur_near = False
    m._pomo_win()
    m.root.update()
    wins = run_phase(m, "같이·창열림·가만히", 14, wins)
    m._cur_near = True
    wins = run_phase(m, "같이·창열림·커서곁", 14, wins)
    m._cur_near = False
    try:
        m._pomo_winref.destroy()
    except Exception:
        pass
    m._team_fold()
    wins = run_phase(m, "접은 뒤·가만히", 10, wins)
except _Skip:
    pass
except Exception as e:
    import traceback
    print("[진단] 같이하기 단계 실패 %r" % e, flush=True)
    traceback.print_exc()

for want in (() if ONLY_BGM else ("만두", "고양이")):
    pick = next((k for k, v in m._prop_layout.items()
                 if isinstance(v, dict) and v.get("gname") == want), None)
    print("[진단] 소품 강제: %s = %s" % (want, pick), flush=True)
    if pick:
        try:
            m._pick_prop = (lambda p=pick: p)
            t1 = time.time()
            m._load_parts()
            print("[진단] %s 파츠 로드 %.2fs" % (want, time.time() - t1),
                  flush=True)
        except Exception as e:
            print("[진단] %s 로드 실패 %r" % (want, e), flush=True)
    wins = run_phase(m, want, 18, wins)

# ── 패널(할 일·마감) 재현 — '검은 줄' 제보의 창들을 실제로 띄운다 ──
def dump_filters(tag):
    """창마다 색상키 필터·색공간이 걸렸는지 덤프한다."""
    try:
        from AppKit import NSApplication
        ck = getattr(m, "_mac_ck", None)
        want = getattr(ck, "filter", None)
        for w in NSApplication.sharedApplication().windows():
            try:
                f = w.frame()
                cv = w.contentView()
                lay = cv.layer() if cv else None
                filt = lay.compositingFilter() if lay is not None else None
                on = (filt == want) if want is not None else bool(filt)
                cs = ""
                try:
                    cs = str(w.colorSpace().localizedName())
                except Exception:
                    pass
                print("[필터:%s] #%d %4dx%-4d 보임=%s 필터=%s 색공간=%s"
                      % (tag, w.windowNumber(), int(f.size.width),
                         int(f.size.height), bool(w.isVisible()),
                         "걸림" if on else "!! 없음", cs), flush=True)
            except Exception as e:
                print("[필터:%s] 창 하나 실패 %r" % (tag, e), flush=True)
    except Exception as e:
        print("[필터] 덤프 실패 %r" % e, flush=True)


# ── 띠 우클릭 반응 메뉴 (사가 제보: 새하얗게 뜨고 못 누른다) ──────────
def probe_popup():
    """_strip_popup 을 실제로 띄워 본다 — 그려졌나·필터가 걸렸나·픽셀은?"""
    try:
        team_setup(m)
    except Exception as e:
        print("[팝업] 같이하기 세우기 실패 %r" % e, flush=True)
    for _ in range(60):                     # 띠가 한 번 그려질 때까지
        m.root.update()
        time.sleep(0.02)
    print("[팝업] 띠 사람수=%s cols=%s"
          % (len(m._strip_who or []), getattr(m, "_strip_cols", None)),
          flush=True)
    items = m._strip_react_menu(
        (m._strip_who or [(m.char,)])[0][0] if m._strip_who else m.char)
    win = m._strip_popup(items, 200, 200)
    for _ in range(40):
        m.root.update()
        time.sleep(0.02)
    try:
        cv9 = [w for w in win.winfo_children() if w.winfo_class() == "Canvas"]
        n_items = len(cv9[0].find_all()) if cv9 else -1
        n_text = (len([i for i in cv9[0].find_all()
                       if cv9[0].type(i) == "text"]) if cv9 else -1)
    except Exception as e:
        n_items = n_text = "err %r" % e
    print("[팝업] 캔버스 조각 %s개 (글자 %s개) · 크기 %sx%s at(%s,%s)"
          % (n_items, n_text, win.winfo_width(), win.winfo_height(),
             win.winfo_rootx(), win.winfo_rooty()), flush=True)
    # 이 창의 NSWindow — 클래스·styleMask·필터가 걸렸는지
    try:
        from AppKit import NSApplication
        ck = getattr(m, "_mac_ck", None)
        want = getattr(ck, "filter", None)
        for w in NSApplication.sharedApplication().windows():
            try:
                f = w.frame()
                if abs(int(f.size.width) - win.winfo_width()) > 2:
                    continue
                cv = w.contentView()
                lay = cv.layer() if cv else None
                filt = lay.compositingFilter() if lay is not None else None
                on = (filt == want) if want is not None else bool(filt)
                print("[팝업] NSWindow %s style=%s %dx%d 필터=%s 배경알파=%s"
                      % (w.className(), int(w.styleMask()),
                         int(f.size.width), int(f.size.height),
                         "걸림" if on else "없음",
                         w.backgroundColor().alphaComponent()), flush=True)
            except Exception as e:
                print("[팝업] 창 하나 실패 %r" % e, flush=True)
    except Exception as e:
        print("[팝업] NSWindow 훑기 실패 %r" % e, flush=True)
    # 픽셀 — 팝업 자리를 찍어 무슨 색인지 (글자가 있으면 색이 여러 가지)
    try:
        ck = getattr(m, "_mac_ck", None)
        if ck is not None:
            got = ck.probe(win.winfo_width(), [(20, 12), (60, 12), (20, 40)])
            print("[팝업픽셀] (20,12)/(60,12)/(20,40) ARGB = %s" % (got,),
                  flush=True)
    except Exception as e:
        print("[팝업픽셀] 실패 %r" % e, flush=True)
    try:
        win.destroy()
        m._team_fold()
    except Exception:
        pass


try:
    if ONLY_BGM or getattr(M, "IS_MAC", False):
        # 맥의 띠 메뉴는 이제 tk.Menu 다 — 띄우면 사람이 고를 때까지
        # 멈춘다. 러너에는 사람이 없어 30분 제한까지 걸린다 (지뢰 49).
        print("[팝업] 건너뜀 — 맥은 OS 메뉴라 띄우면 멈춘다 (지뢰 49)",
              flush=True)
        raise _Skip()
    probe_popup()
except _Skip:
    pass
except Exception as e:
    import traceback
    print("[팝업] 검사 실패 %r" % e, flush=True)
    traceback.print_exc()

if not ONLY_BGM:
    dump_filters("패널 넣기 전")
try:
    if ONLY_BGM:
        raise _Skip()
    if m.todo_panel is not None:
        m.todos = [{"t": "진단 할 일", "done": False}]
        try:
            m.todo_panel.render(m.todos)
        except Exception:
            m.todo_panel.render(["진단 할 일"])
        m.todo_panel.place(m.root.winfo_rootx(), m.root.winfo_rooty())
    if m.due_panel is not None:
        m.due_panel.render(["D-3 진단 마감"], ["#d64a63"])
        m.due_panel.place(m.root.winfo_rootx(), m.root.winfo_rooty())
    print("[패널] 할 일·마감을 띄웠다", flush=True)
except _Skip:
    pass
except Exception as e:
    print("[패널] 띄우기 실패 %r" % e, flush=True)
# 색상키 주기가 새 창을 잡을 시간을 주고 다시 덤프
t9 = time.time()
while (not ONLY_BGM) and time.time() - t9 < 5.0:
    try:
        m.root.update()
    except Exception:
        break
    time.sleep(0.01)
if not ONLY_BGM:
    dump_filters("패널 넣은 뒤")
# 패널 픽셀 — 폭 790(패널) 창을 찍어 투명한지 본다
try:
    ck = getattr(m, "_mac_ck", None)
    if ck is not None:
        for pw in (790,):
            got = ck.probe(pw, [(20, 5), (pw // 2, 5)])
            print("[패널픽셀] 폭 %d 창 (20,5)/(중앙,5) = %s" % (pw, got),
                  flush=True)
except Exception as e:
    print("[패널픽셀] 실패 %r" % e, flush=True)

# ── '검은 막대' 재현 검사 — 빈 패널을 place/raise 로 계속 건드려도
# 화면에 안 올라와야 한다 (사가 사고의 시나리오 그대로).
try:
    if ONLY_BGM:
        raise _Skip()
    from AppKit import NSApplication
    tp = m.todo_panel
    dp = m.due_panel
    for pn, nm in ((tp, "할일"), (dp, "마감")):
        if pn is None:
            continue
        pn.render([])                       # 비움 → withdraw
    for i in range(200):                    # 그리기 루프 흉내
        for pn in (tp, dp):
            if pn is None:
                continue
            pn.place(m.root.winfo_rootx(), m.root.winfo_rooty())
            pn.raise_above()
        m.root.update()
        time.sleep(0.005)
    bad9 = []
    for w in NSApplication.sharedApplication().windows():
        try:
            f = w.frame()
            if f.size.height <= 14 and f.size.width > 300 and w.isVisible():
                bad9.append("%dx%d" % (f.size.width, f.size.height))
        except Exception:
            pass
    print("[막대] 빈 패널 place/raise 200번 뒤 보이는 납작 창: %s"
          % (bad9 or "없음(정상)"), flush=True)
    ck9 = getattr(m, "_mac_ck", None)
    if ck9 is not None:
        for line in ck9.scan_all():
            print("[막대스캔] " + line, flush=True)
except _Skip:
    pass
except Exception as e:
    print("[막대] 검사 실패 %r" % e, flush=True)

# ── 매끈 레이어 채움 검증 — GPU 확대(contentsScale=1)가 창을 꽉
# 채우는가. 예전 '절반 크기' 사고(contentsScale=2 + 1배 그림)의 재발을
# 픽셀로 잡는다: 창 세로 82% 지점(책상)이 불투명해야 한다.
try:
    ck = getattr(m, "_mac_ck", None)
    W9 = m.root.winfo_width()
    H9 = m.root.winfo_height()
    if ck is not None:
        pts = [(W9 // 2, int(H9 * 0.82)), (W9 // 2, int(H9 * 0.55)),
               (W9 // 2, 2)]
        got = ck.probe(W9, pts)
        print("[채움] 창 %dx%d 중앙 82%%/55%%/위끝 ARGB = %s" % (W9, H9, got),
              flush=True)
        if got and len(got) >= 2:
            a_desk = (got[0][0] if isinstance(got[0], (list, tuple)) else 0)
            print("[채움] 책상 자리 알파=%s → %s" % (
                a_desk, "채워짐(정상)" if a_desk and a_desk > 30
                else "!! 비었다 — 절반 크기 재발 의심"), flush=True)
except Exception as e:
    print("[채움] 검증 실패 %r" % e, flush=True)

# ── 색상키 실검증 (검은 줄 — 지워지는지 합성 결과를 직접 읽는다) ──
try:
    m._safe("mac_verify", m._mac_verify)
except Exception as e:
    print("[진단] mac_verify 실패 %r" % e, flush=True)
try:
    m.root.update()
except Exception:
    pass

# ── 플레이리스트 창 (새 기능) — 맥에서 실제로 도는가 ────────────────
# 브리핑의 네 단계: 창 열기 · 긴 제목 호버 · 재생 중(이퀄라이저 + 지금 곡)
# · 환경음 탭. 단계마다 프레임 시간·CPU% 를 재고, **표시줄이 있는 창이라
# 색상키 필터가 안 걸리는지**(지뢰 126) 같이 본다. 찍은 그림은 shots/ 로.


def probe_bgm(prev_wins):
    """플레이리스트 창 — 열기·호버·재생 중·환경음 탭."""
    m._yt_avail = True
    m._yt_send = lambda **kw: None
    m._pl_fetch_title = lambda url: None      # 그물 밖으로 안 나간다
    m.us["yt_signed"] = True
    m.us["yt_asked"] = True
    # 아래 '지금 곡' 은 창 폭에 가까우니 넉넉히 길게 (화면 배율이 커도 잘리게)
    LONG = ("아주 긴 노래 제목 그리고 부제까지 붙은 아주 아주 긴 이름 "
            "그리고 뒤에 더 붙는 아주 긴 꼬리표까지")
    songs = [{"u": "https://youtu.be/x%08d" % i,
              "t": (LONG if i == 0 else "짧은 곡 %d" % i),
              "a": "가수 %d" % i, "d": 201 + i} for i in range(8)]
    m.us["yt_sets"] = [songs, [], []]
    m.us["yt_set_i"] = 0
    win = m._bgm_win("pl")
    m.root.update()
    cvs = [w for w in win.winfo_children() if w.winfo_class() == "Canvas"]
    cv9 = cvs[0] if cvs else None
    st9 = m._bgm_st
    print("[플리] 창 %dx%d · 표시줄없음=%s · 크기조절=%s · 캔버스 조각 %d개"
          % (win.winfo_width(), win.winfo_height(),
             bool(win.overrideredirect()), win.resizable(),
             len(cv9.find_all()) if cv9 is not None else -1), flush=True)
    print("[플리] 프리셋 %d벌 · 지금 %d번 · 곡 %d · 단추 %d개"
          % (len(m.us.get("yt_sets") or []), m._pl_set_i(),
             len(m._pl_list()),
             len([h for h in st9["hits"] if h[4] == "set"])), flush=True)
    # 이 창에 색상키 필터가 걸리면 안 된다 (제목 표시줄이 있으니 · 지뢰 126)
    try:
        from AppKit import NSApplication
        ck9 = getattr(m, "_mac_ck", None)
        want9 = getattr(ck9, "filter", None)
        for w9 in NSApplication.sharedApplication().windows():
            f9 = w9.frame()
            if abs(int(f9.size.width) - win.winfo_width()) > 4:
                continue
            cv0 = w9.contentView()
            lay9 = cv0.layer() if cv0 else None
            filt9 = lay9.compositingFilter() if lay9 is not None else None
            on9 = (filt9 == want9) if want9 is not None else bool(filt9)
            print("[플리] NSWindow style=%d 필터=%s → %s"
                  % (int(w9.styleMask()), "걸림" if on9 else "없음",
                     "!! 걸리면 안 된다" if on9 else "정상"), flush=True)
    except Exception as e:
        print("[플리] NSWindow 훑기 실패 %r" % e, flush=True)
    prev_wins = run_phase(m, "플리·창열림", 8, prev_wins)
    grab_window(win, "bgm_pl")

    # ② 긴 제목에 커서 — 흐르는 글자 (마퀴)
    offs = set()
    tgt = next((t for t in (st9.get("titles") or []) if not t[5]), None)
    if tgt is not None and cv9 is not None:
        cv9.event_generate("<Motion>", x=int((tgt[0] + tgt[2]) / 2),
                           y=int((tgt[1] + tgt[3]) / 2))
        m.root.update()
    print("[플리] 긴 제목 자리=%s · 호버=%s"
          % (tgt is not None, st9.get("hov")), flush=True)
    prev_wins = run_phase(m, "플리·제목 호버", 6, prev_wins,
                          probe=lambda: offs.add(getattr(m, "_pl_mq_off", -1)))
    print("[플리] 흐른 자리 %d가지 (%s …) → %s"
          % (len(offs), sorted(offs)[:5],
             "흐른다" if len(offs) >= 3 else "!! 안 흐른다"), flush=True)
    grab_window(win, "bgm_hover")
    if cv9 is not None:
        cv9.event_generate("<Leave>")
        m.root.update()

    # ③ 재생 중 — 이퀄라이저가 오르내리고 아래 '지금 곡' 이 선다
    m._pl_src = "mine"
    m._pl_on = True
    m._pl_i = 0
    m._pl_url = songs[0]["u"]
    m._bgm_redraw()
    m.root.update()
    nb9 = st9.get("nowbox")
    print("[플리] 이퀄라이저 자리=%s · 지금 곡 자리=%s (잘림=%s)"
          % (st9.get("eq"), nb9 is not None,
             (not nb9[4]) if nb9 else None), flush=True)
    if nb9 is not None and cv9 is not None and not nb9[4]:
        cv9.event_generate("<Motion>", x=int((nb9[0] + nb9[2]) / 2),
                           y=int((nb9[1] + nb9[3]) / 2))
        m.root.update()
    offs2 = set()
    prev_wins = run_phase(m, "플리·재생 중", 8, prev_wins,
                          probe=lambda: offs2.add(
                              getattr(m, "_pl_mq_off", -1)))
    print("[플리] 지금 곡 호버=%s · 흐른 자리 %d가지"
          % (st9.get("hov"), len(offs2)), flush=True)
    grab_window(win, "bgm_playing")

    # ④ 환경음 탭
    m._bgm_win("amb")
    m.root.update()
    n_amb = len([h for h in st9["hits"] if h[4] == "amb_toggle"])
    print("[플리] 환경음 탭 — 줄 %d개" % n_amb, flush=True)
    prev_wins = run_phase(m, "플리·환경음 탭", 6, prev_wins)
    grab_window(win, "bgm_amb")
    m._bgm_win("pl")
    m.root.update()
    try:
        win.destroy()
    except Exception:
        pass
    m._pl_on = False
    m.root.update()
    return prev_wins


try:
    wins = probe_bgm(wins)
except Exception as e:
    import traceback
    print("[플리] 검사 실패 %r" % e, flush=True)
    traceback.print_exc()

# ── 맥 유튜브 재생기 (WKWebView) — 자식으로 띄워 프로토콜 왕복 ──────
# 렉 패치와 같이 들어간 기능. ready → load → playing 까지 실제로 도는지.
print("[진단] yt-player 자식 검사", flush=True)
try:
    import json as _json
    import subprocess
    import threading

    p9 = subprocess.Popen(
        [sys.executable, "-u", os.path.join(HERE, "mascot.py"),
         "--yt-player"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, encoding="utf-8", errors="replace")
    yt_lines = []

    def _yt_rd():
        try:
            for ln in p9.stdout:
                yt_lines.append(ln.strip())
        except Exception:
            pass

    threading.Thread(target=_yt_rd, daemon=True).start()
    time.sleep(7)
    p9.stdin.write(_json.dumps({"c": "vol", "v": 5}) + "\n")
    p9.stdin.write(_json.dumps({"c": "load", "v": "aqz-KE-bpKQ"}) + "\n")
    p9.stdin.flush()
    t9 = time.time()
    while time.time() - t9 < 40:
        if any('"playing": true' in ln for ln in yt_lines):
            break
        time.sleep(1)
    for ln in yt_lines[:30]:
        print("   ", ln[:160], flush=True)
    ok_ready = any('"ready": true' in ln for ln in yt_lines)
    ok_play = any('"playing": true' in ln for ln in yt_lines)
    durs = [ln for ln in yt_lines if '"dur"' in ln]
    print("[yt] dur 실린 줄 %d개%s → %s"
          % (len(durs), (" 예: " + durs[-1][:120]) if durs else "",
             "통과" if durs else "!! 곡 길이가 안 온다"), flush=True)
    print("[yt] ready=%s playing=%s (줄 %d개)"
          % (ok_ready, ok_play, len(yt_lines)), flush=True)
    # 멈춤이 실제로 멈추는가 (사가·퀸시 제보 — '멈춤이 안 먹힌다').
    # pause 를 보내고, 그 뒤로 playing:true 가 다시 나오면 실패다.
    n0 = len(yt_lines)
    p9.stdin.write(_json.dumps({"c": "pause"}) + "\n")
    p9.stdin.flush()
    time.sleep(8)
    after = yt_lines[n0:]
    paused = any('"playing": false' in ln for ln in after)
    revived = any('"playing": true' in ln for ln in after[2:])
    print("[yt] pause 뒤 %d줄 · 멈춤확인=%s · 되살아남=%s → %s"
          % (len(after), paused, revived,
             "통과" if (not revived) else "!! 멈춤이 안 먹힘"), flush=True)
    n1 = len(yt_lines)
    p9.stdin.write(_json.dumps({"c": "play"}) + "\n")
    p9.stdin.flush()
    time.sleep(5)
    resumed = any('"playing": true' in ln for ln in yt_lines[n1:])
    print("[yt] play 로 재개=%s" % resumed, flush=True)
    # ── 영상 칸 (요청) — 창이 정말 그 자리로 오는가 ─────────────────
    def _win_of(pid, want_w=None):
        """그 프로세스의 화면 위 창 — (번호, x, y, w, h, 알파)."""
        try:
            from Quartz import (CGWindowListCopyWindowInfo,
                                kCGWindowListOptionOnScreenOnly,
                                kCGNullWindowID)
        except Exception:
            return None
        try:
            got = []
            for it in (CGWindowListCopyWindowInfo(
                    kCGWindowListOptionOnScreenOnly, kCGNullWindowID) or []):
                if int(it.get("kCGWindowOwnerPID", -1)) != pid:
                    continue
                b = it.get("kCGWindowBounds") or {}
                got.append((int(it.get("kCGWindowNumber") or 0),
                            int(b.get("X", 0)), int(b.get("Y", 0)),
                            int(b.get("Width", 0)), int(b.get("Height", 0)),
                            float(it.get("kCGWindowAlpha", 1.0))))
            if want_w is not None:
                for g in got:
                    if abs(g[3] - want_w) <= 4:
                        return g
            return got[0] if got else None
        except Exception:
            return None

    try:
        BOX = (220, 160, 480, 270)      # 화면 좌표 (왼쪽 위 기준)
        before = _win_of(p9.pid)
        print("[영상] 끼우기 전 창: %s" % (before,), flush=True)
        p9.stdin.write(_json.dumps(
            {"c": "embed", "x": BOX[0], "y": BOX[1], "w": BOX[2],
             "h": BOX[3], "r": 14, "show": 1}) + "\n")
        p9.stdin.flush()
        time.sleep(2.5)
        got9 = _win_of(p9.pid, BOX[2])
        print("[영상] 끼운 뒤 창: %s (바라던 자리 %s)" % (got9, BOX), flush=True)
        if got9:
            okpos = (abs(got9[1] - BOX[0]) <= 2 and abs(got9[2] - BOX[1]) <= 2
                     and abs(got9[3] - BOX[2]) <= 2
                     and abs(got9[4] - BOX[3]) <= 2)
            print("[영상] 자리 맞음=%s · 알파=%.2f → %s"
                  % (okpos, got9[5],
                     "보인다" if got9[5] > 0.5 else "!! 안 보인다"), flush=True)
        # 그 자리를 찍어 어두운(영상) 픽셀이 있는지
        try:
            import Quartz
            from Quartz import (CGRectMake, CGImageDestinationCreateWithURL,
                                CGImageDestinationAddImage,
                                CGImageDestinationFinalize)
            from Foundation import NSURL
            os.makedirs(SHOTS, exist_ok=True)
            img9 = Quartz.CGWindowListCreateImage(
                CGRectMake(BOX[0], BOX[1], BOX[2], BOX[3]),
                Quartz.kCGWindowListOptionOnScreenOnly, 0,
                Quartz.kCGWindowImageDefault)
            if img9 is not None:
                pth = os.path.join(SHOTS, "video.png")
                d9 = CGImageDestinationCreateWithURL(
                    NSURL.fileURLWithPath_(pth), "public.png", 1, None)
                CGImageDestinationAddImage(d9, img9, None)
                CGImageDestinationFinalize(d9)
                print("[영상] 그 자리 찍음 %dx%d"
                      % (Quartz.CGImageGetWidth(img9),
                         Quartz.CGImageGetHeight(img9)), flush=True)
        except Exception as e9:
            print("[영상] 찍기 실패 %r" % e9, flush=True)
        # 숨기기·다시 보이기
        for on9 in (0, 1):
            p9.stdin.write(_json.dumps({"c": "vidshow", "on": on9}) + "\n")
            p9.stdin.flush()
            time.sleep(1.2)
            g9 = _win_of(p9.pid, BOX[2])
            print("[영상] vidshow %d → 알파 %s"
                  % (on9, ("%.2f" % g9[5]) if g9 else "?"), flush=True)
        # 자리 옮기기
        p9.stdin.write(_json.dumps(
            {"c": "vidbox", "x": BOX[0] + 60, "y": BOX[1] + 40,
             "w": BOX[2], "h": BOX[3], "r": 14}) + "\n")
        p9.stdin.flush()
        time.sleep(1.5)
        g9 = _win_of(p9.pid, BOX[2])
        print("[영상] 옮긴 뒤 창: %s (바라던 %s)"
              % (g9, (BOX[0] + 60, BOX[1] + 40)), flush=True)
        # 떼기
        p9.stdin.write(_json.dumps({"c": "unembed"}) + "\n")
        p9.stdin.flush()
        time.sleep(1.5)
        g9 = _win_of(p9.pid)
        print("[영상] 뗀 뒤 창: %s" % (g9,), flush=True)
        n9 = len(yt_lines)
        time.sleep(3)
        still = any('"playing": true' in ln for ln in yt_lines[n9:])
        print("[영상] 그 뒤에도 소리가 나는가=%s → %s"
              % (still, "통과" if still else "!! 재생이 끊겼다"), flush=True)
    except Exception as e9:
        import traceback
        print("[영상] 검사 실패 %r" % e9, flush=True)
        traceback.print_exc()

    try:
        p9.stdin.write(_json.dumps({"c": "quit"}) + "\n")
        p9.stdin.flush()
        p9.wait(timeout=8)
        print("[yt] quit → 종료 코드", p9.returncode, flush=True)
    except Exception:
        p9.kill()
        print("[yt] quit 안 먹어 kill", flush=True)
except Exception as e:
    print("[yt] 검사 실패 %r" % e, flush=True)

print("[진단] 종료 — 기록을 쏟는다", flush=True)
try:
    m.close()
except Exception:
    pass
for name in (".error.log", ".macwindow.log", ".yt_err.txt"):
    p = os.path.join(HERE, CHAR, name)
    if os.path.exists(p):
        print("── %s ──" % name, flush=True)
        try:
            body = open(p, encoding="utf-8", errors="replace").read()
            print(body[-4000:], flush=True)
        except Exception as e:
            print("읽기 실패 %r" % e, flush=True)
print("[진단] 끝", flush=True)
