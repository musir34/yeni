# gorev.py
from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo
import logging
from functools import wraps

from flask import Blueprint, request, jsonify, redirect, url_for, flash, render_template, session
from flask_login import login_required, current_user

from models import db, Task, TaskTemplate, MasterTask, User

IST = ZoneInfo("Europe/Istanbul")
log = logging.getLogger(__name__)
gorev_bp = Blueprint("gorev", __name__)

# ───────────────────────── Helpers ─────────────────────────
def _today_ist() -> date:
    return datetime.now(IST).date()

def _week_start(d: date) -> date:
    # Pazartesi = 0
    return d - timedelta(days=d.weekday())

def _week_end_dt(d: date) -> datetime:
    ws = _week_start(d)
    # Pazar 18:00 varsayalım (sen istersen değiştir)
    return datetime.combine(ws + timedelta(days=6), time(hour=18, minute=0), IST)

def _is_admin():
    role = session.get("role") or getattr(current_user, "role", None)
    return role in ("admin", "manager")

def admin_required(f):
    @wraps(f)
    def _wrap(*a, **k):
        if not _is_admin():
            flash("Bu sayfaya erişim yetkiniz yok.", "danger")
            return redirect(url_for("home.home"))
        return f(*a, **k)
    return _wrap

# ────────────────── HAFTALIK ANA GÖREV ÜRETİMİ ──────────────────
def generate_week_main_tasks(ref: date | None = None) -> int:
    ref = ref or _today_ist()
    ws = _week_start(ref)                                     # haftanın pazartesisi (tarih)
    created = 0
    for t in TaskTemplate.query.filter_by(active=True).all():
        if Task.query.filter_by(assignee=t.assignee, title=t.title, date_=ws).first():
            continue
        week_created_dt = datetime.combine(ws, time(0,0), IST) # Pazartesi 00:00
        task = Task(
            assignee=t.assignee, assignee_email=t.assignee_email, title=t.title,
            date_=ws,                 # haftanın tarihi (PAZARTESİ)
            due=week_created_dt,      # sadece placeholder (esnekte hatırlatma için kullanmayacağız)
            priority=t.priority, proof_required=t.proof_required,
            created_at=week_created_dt
        )
        if hasattr(Task, "flexible"):         task.flexible = True
        if hasattr(Task, "expected_window"):  task.expected_window = "this_week"
        if hasattr(Task, "commit_due"):       task.commit_due = None
        if hasattr(Task, "commit_at"):        task.commit_at  = None
        db.session.add(task); created += 1
    db.session.commit()
    return created


# ───────────── Günlük klasik (istersen kalsın, ana akış haftalık) ─────────────
def generate_today_tasks() -> int:
    today = _today_ist()
    wd = str(today.weekday())  # Mon=0 ... Sun=6
    created = 0
    for t in TaskTemplate.query.filter_by(active=True).all():
        if wd not in (t.weekdays or ""):
            continue
        due_dt = datetime.combine(today, time(hour=t.due_h, minute=t.due_m), IST)
        exists = Task.query.filter_by(assignee=t.assignee, title=t.title, date_=today).first()
        if exists:
            continue
        task = Task(
            assignee=t.assignee, assignee_email=t.assignee_email, title=t.title,
            date_=today, due=due_dt, priority=t.priority, proof_required=t.proof_required
        )
        # Günlük görevlerde de esnek olsun istersen:
        if hasattr(Task, "flexible"):
            task.flexible = True
        if hasattr(Task, "expected_window"):
            task.expected_window = "today"
        db.session.add(task); created += 1
    db.session.commit()
    return created

# ───────────────────────── Reminders ─────────────────────────
def _send_mail_stub(to, subject, body):
    # 1-2 güne WhatsApp burada; şimdilik log
    if to:
        log.info(f"[REMINDER] to={to} subj={subject} body={body[:120]}")

def reminders_job(app=None):
    """
    APScheduler job - Flask app context gerektirir.
    app parametresi attach_jobs içinde lambda ile sağlanır.
    """
    if app is None:
        from flask import current_app
        app = current_app._get_current_object()
    
    with app.app_context():
        now = datetime.now(IST)
        q = Task.query.filter(Task.status.in_(["bekliyor", "yapiliyor"]))
        for t in q.all():
            # esnek ve taahhüt verilmemişse hatırlatma yapma
            if getattr(t, "flexible", False) and getattr(t, "commit_due", None) is None:
                continue
            ref_dt = getattr(t, "commit_due", None) or t.due
            mins_left = (ref_dt - now).total_seconds() / 60
            if 29.5 < mins_left <= 30 and not t.reminded_30:
                _send_mail_stub(getattr(t,"assignee_email",None), f"30 dk kaldı: {t.title}", "Yaklaşıyor.")
                t.reminded_30 = True
            if 9.5 < mins_left <= 10 and not t.reminded_10:
                _send_mail_stub(getattr(t,"assignee_email",None), f"10 dk kaldı: {t.title}", "Hadi bitirelim.")
                t.reminded_10 = True
            if mins_left < 0 and t.status in ("bekliyor","yapiliyor"):
                t.status = "gecikti"
        db.session.commit()


# ───────────────────────── Admin UI Panel ─────────────────────────
@gorev_bp.route("/panel", methods=["GET"])
@login_required
@admin_required
def gorev_panel():
    users = (
        User.query.with_entities(User.id, User.first_name, User.last_name, User.email)
        .order_by(User.first_name, User.last_name)
        .all()
    )
    # Bugün ve bu haftanın başlangıcı
    today = _today_ist()
    ws = _week_start(today)

    tasks_today = Task.query.filter_by(date_=today).order_by(Task.priority, Task.due).all()
    tasks_week  = Task.query.filter_by(date_=ws).order_by(Task.priority, Task.due).all()
    templates   = TaskTemplate.query.order_by(TaskTemplate.assignee, TaskTemplate.title).all()
    return render_template(
        "gorev_panel.html",
        users=users, tasks_today=tasks_today, templates=templates,
        tasks_week=tasks_week
    )

# ───────────────────────── Katalog (Ana Görevler) ─────────────────────────
@gorev_bp.route("/catalog/create", methods=["POST"])
@login_required
@admin_required
def catalog_create():
    d = request.get_json(force=True)
    m = MasterTask(
        title=d["title"].strip(),
        description=d.get("description"),
        default_due_h=int(d.get("due_h",11)),
        default_due_m=int(d.get("due_m",0)),
        default_weekdays=d.get("weekdays","0,1,2,3,4"),
        default_priority=int(d.get("priority",2)),
        proof_required=bool(d.get("proof_required", False)),
        active=bool(d.get("active", True)),
    )
    db.session.add(m); db.session.commit()
    return jsonify(ok=True, id=m.id)

@gorev_bp.route("/catalog/list", methods=["GET"])
@login_required
@admin_required
def catalog_list():
    rows = MasterTask.query.order_by(MasterTask.active.desc(), MasterTask.title).all()
    return jsonify(items=[{
        "id": r.id, "title": r.title, "active": r.active,
        "weekdays": r.default_weekdays, "due_h": r.default_due_h, "due_m": r.default_due_m,
        "priority": r.default_priority, "proof_required": r.proof_required
    } for r in rows])

@gorev_bp.route("/catalog/update/<int:mid>", methods=["POST"])
@login_required
@admin_required
def catalog_update(mid):
    d = request.get_json(force=True)
    m = MasterTask.query.get_or_404(mid)
    if "title" in d: m.title = d["title"].strip()
    if "description" in d: m.description = d["description"]
    if "default_weekdays" in d: m.default_weekdays = d["default_weekdays"]
    if "due_h" in d: m.default_due_h = int(d["due_h"])
    if "due_m" in d: m.default_due_m = int(d["due_m"])
    if "priority" in d: m.default_priority = int(d["priority"])
    if "proof_required" in d: m.proof_required = bool(d["proof_required"])
    if "active" in d: m.active = bool(d["active"])
    db.session.commit()
    return jsonify(ok=True)

@gorev_bp.route("/catalog/delete/<int:mid>", methods=["POST"])
@login_required
@admin_required
def catalog_delete(mid):
    m = MasterTask.query.get_or_404(mid)
    m.active = False  # soft
    db.session.commit()
    return jsonify(ok=True)

# ─────────── Katalogtan ŞABLON DAĞIT (kime ana görev verilecek?) ───────────
@gorev_bp.route("/distribute", methods=["POST"])
@login_required
@admin_required
def distribute():
    d = request.get_json(force=True)
    m = MasterTask.query.get_or_404(int(d["master_task_id"]))
    user_ids = d.get("user_ids", [])
    weekdays = d.get("weekdays", m.default_weekdays)
    due_h = int(d.get("due_h", m.default_due_h))
    due_m = int(d.get("due_m", m.default_due_m))
    priority = int(d.get("priority", m.default_priority))
    created = 0
    for uid in user_ids:
        u = User.query.get(int(uid))
        if not u: 
            continue
        tpl = TaskTemplate(
            master_task_id=m.id,
            assignee=f"{(u.first_name or '').strip()} {(u.last_name or '').strip()}".strip() or (u.email or "Kullanıcı"),
            assignee_email=u.email,
            title=m.title,
            due_h=due_h, due_m=due_m,
            weekdays=weekdays, priority=priority,
            proof_required=m.proof_required, active=True
        )
        db.session.add(tpl); created += 1
    db.session.commit()
    return jsonify(ok=True, created=created)

# ───────────────────────── “Yan Görev” (gün içi) ─────────────────────────
@gorev_bp.route("/side/add", methods=["POST"])
@login_required
@admin_required
def side_add():
    """
    Gün içinde çıkan sorunlar için hızlı görev.
    Saat vermiyorsun → esnek; çalışan taahhüt edecek.
    """
    d = request.get_json(force=True)
    u = User.query.get_or_404(int(d["user_id"]))
    title = (d.get("title") or "").strip()
    if not title:
        return jsonify(ok=False, err="title_required"), 400

    today = _today_ist()
    # esnek yan görevler için “due” emniyet: bugün 23:59
    due_dt = datetime.combine(today, time(23, 59), IST)
    t = Task(
        assignee=f"{(u.first_name or '').strip()} {(u.last_name or '').strip()}".strip() or (u.email or "Kullanıcı"),
        assignee_email=u.email,
        title=title,
        date_=today,
        due=due_dt,
        priority=int(d.get("priority", 2)),
        proof_required=bool(d.get("proof_required", False)),
    )
    if hasattr(Task, "flexible"): t.flexible = True
    if hasattr(Task, "expected_window"): t.expected_window = "today"
    if hasattr(Task, "acceptance"): t.acceptance = (d.get("acceptance") or "").strip()
    if hasattr(Task, "effort"): t.effort = int(d.get("effort", 1))

    db.session.add(t); db.session.commit()
    return jsonify(ok=True, id=t.id)

# ───────────────────────── Çalışan: Taahhüt ver ─────────────────────────
@gorev_bp.route("/task/commit", methods=["POST"])
@login_required
def task_commit():
    d = request.get_json(force=True)
    t = Task.query.get_or_404(int(d["task_id"]))
    # Güvenlik: kullanıcı kendi görevine taahhüt edebilir; admin herkesinkine
    me_full = (session.get("first_name","") + " " + session.get("last_name","")).strip()
    if not _is_admin() and t.assignee.strip() != me_full:
        return jsonify(ok=False, err="forbidden"), 403

    commit_due_str = d.get("commit_due")  # 'YYYY-MM-DDTHH:MM' (veya ISO)
    try:
        commit_due = datetime.fromisoformat(commit_due_str)
        if commit_due.tzinfo is None:
            commit_due = commit_due.replace(tzinfo=IST)
    except Exception:
        return jsonify(ok=False, err="bad_datetime"), 400

    if hasattr(Task, "commit_due"): t.commit_due = commit_due
    if hasattr(Task, "commit_at"):  t.commit_at  = datetime.now(IST)
    # esnek mod açık değilse bile commit varsayımını kabul edelim
    db.session.commit()
    return jsonify(ok=True)

# ───────────────────────── Çalışan: Tamamla ─────────────────────────
@gorev_bp.route("/task/complete", methods=["POST"])
@login_required
def task_complete():
    d = request.get_json(force=True)
    t = Task.query.get_or_404(int(d["task_id"]))
    me_full = (session.get("first_name","") + " " + session.get("last_name","")).strip()
    if not _is_admin() and t.assignee.strip() != me_full:
        return jsonify(ok=False, err="forbidden"), 403

    t.status = "bitti"
    # İstersen kısa not/görsel url’si
    note = (d.get("note") or "").strip()
    if note and hasattr(Task, "proof_url"):
        t.proof_url = note
    db.session.commit()
    return jsonify(ok=True)

# ───────────────────────── Re-assign / Delete ─────────────────────────
@gorev_bp.route("/task/reassign", methods=["POST"])
@login_required
@admin_required
def task_reassign():
    d = request.get_json(force=True)
    t = Task.query.get_or_404(int(d["task_id"]))
    u = User.query.get_or_404(int(d["new_user_id"]))
    t.assignee = f"{(u.first_name or '').strip()} {(u.last_name or '').strip()}".strip() or (u.email or "Kullanıcı")
    t.assignee_email = u.email
    db.session.commit()
    return jsonify(ok=True)

@gorev_bp.route("/task/delete", methods=["POST"])
@login_required
@admin_required
def task_delete():
    d = request.get_json(force=True)
    t = Task.query.get_or_404(int(d["task_id"]))
    # Soft-delete yapmak istersen models/DB’de deleted_at kolonu ekleyip işaretleyebilirsin.
    db.session.delete(t)
    db.session.commit()
    return jsonify(ok=True)

@gorev_bp.route("/template/reassign", methods=["POST"])
@login_required
@admin_required
def template_reassign():
    d = request.get_json(force=True)
    tpl = TaskTemplate.query.get_or_404(int(d["template_id"]))
    u = User.query.get_or_404(int(d["new_user_id"]))
    tpl.assignee = f"{(u.first_name or '').strip()} {(u.last_name or '').strip()}".strip() or (u.email or "Kullanıcı")
    tpl.assignee_email = u.email
    db.session.commit()
    return jsonify(ok=True)

@gorev_bp.route("/template/delete", methods=["POST"])
@login_required
@admin_required
def template_delete():
    d = request.get_json(force=True)
    tpl = TaskTemplate.query.get_or_404(int(d["template_id"]))
    db.session.delete(tpl); db.session.commit()
    return jsonify(ok=True)

# ───────────────────────── Klasik (JSON API) ─────────────────────────
@gorev_bp.route("/sablon/ekle", methods=["POST"])
def sablon_ekle():
    d = request.get_json(force=True)
    tpl = TaskTemplate(
        assignee=d["assignee"],
        assignee_email=d.get("assignee_email"),
        title=d["title"],
        due_h=int(d.get("due_h", 11)),
        due_m=int(d.get("due_m", 0)),
        weekdays=d.get("weekdays", "0,1,2,3,4"),
        priority=int(d.get("priority", 2)),
        proof_required=bool(d.get("proof_required", False)),
        active=bool(d.get("active", True)),
    )
    db.session.add(tpl); db.session.commit()
    return jsonify(ok=True, id=tpl.id)

@gorev_bp.route("/bugun/dagit", methods=["POST"])
def bugun_dagit():
    return jsonify(ok=True, created=generate_today_tasks())

@gorev_bp.route("/hafta/dagit", methods=["POST"])
@login_required
@admin_required
def hafta_dagit():
    return jsonify(ok=True, created=generate_week_main_tasks())

@gorev_bp.route("/update", methods=["POST"])
def update_task():
    d = request.get_json(force=True)
    t = Task.query.get(int(d["id"]))
    if not t:
        return jsonify(ok=False, err="not_found"), 404
    # aşamalar: bekliyor / çalışılıyor / bitti / başarısız
    if "status" in d:
        t.status = d["status"]
    if "note" in d:
        t.note = (d["note"] or "").strip()
    if "proof_url" in d:
        t.proof_url = d["proof_url"] or None
    db.session.commit()
    return jsonify(ok=True)


@gorev_bp.route("/kanban", methods=["GET"])
def kanban_json():
    cols = {"bekliyor": [], "yapiliyor": [], "bitti": [], "gecikti": []}
    today = _today_ist()
    q = Task.query.filter(Task.date_ >= _week_start(today)).order_by(Task.priority, Task.due)
    for t in q.all():
        cols[t.status].append({
            "id": t.id, "assignee": t.assignee, "title": t.title,
            "due": t.due.astimezone(IST).strftime("%Y-%m-%d %H:%M"),
            "priority": t.priority,
            "flexible": getattr(t, "flexible", True),
            "commit_due": (t.commit_due.astimezone(IST).strftime("%Y-%m-%d %H:%M") if getattr(t,"commit_due",None) else None)
        })
    return jsonify(range=f"{_week_start(today)}..{_week_start(today)+timedelta(days=6)}", columns=cols)

# ───────────────────────── Scheduler bağlayıcı ─────────────────────────
def attach_jobs(scheduler, app):
    """
    Scheduler'a job'ları ekler. app instance'ı job'lara context sağlamak için kullanılır.
    """
    # Haftalık görev oluşturma (Pazartesi 00:00)
    scheduler.add_job(
        lambda: generate_week_main_tasks_with_context(app), 
        "cron",
        day_of_week="mon", hour=0, minute=0, timezone=str(IST),
        id="gv_weekly", replace_existing=True
    )
    
    # Görev hatırlatıcılar (Her 5 dakika)
    scheduler.add_job(
        lambda: reminders_job(app), 
        "interval", 
        minutes=5, 
        id="gv_rem", 
        replace_existing=True
    )
    
    # 🛒 WooCommerce sipariş senkronizasyonu (Her 10 dakika)
    scheduler.add_job(
        lambda: sync_woocommerce_orders(app),
        "interval",
        minutes=10,
        id="woo_sync",
        replace_existing=True
    )

def generate_week_main_tasks_with_context(app):
    """Haftalık görev oluşturmayı Flask app context içinde yapar."""
    with app.app_context():
        return generate_week_main_tasks()


def sync_woocommerce_orders(app):
    """
    WooCommerce siparişlerini otomatik olarak senkronize eder.
    Trendyol pull_orders_job mantığıyla aynı - her 10 dakikada çalışır.
    """
    with app.app_context():
        try:
            from woocommerce_site.woo_service import WooCommerceService
            from woocommerce_site.woo_config import WooConfig
            
            # API ayarları kontrolü
            if not WooConfig.is_configured():
                log.warning("🛒 WooCommerce API ayarları yapılmamış, senkronizasyon atlandı")
                return
            
            log.info("🛒 WooCommerce sipariş senkronizasyonu başlıyor...")
            
            woo_service = WooCommerceService()
            
            # Aktif siparişleri çek (son 7 gün)
            # on-hold: Sipariş hazırla ekranına düşecek
            # processing: Paketleme tamamlanmış, kargo bekleniyor
            # pending: Ödeme bekleyen siparişler
            active_statuses = ['on-hold', 'processing', 'pending']
            total_saved = 0
            
            for status in active_statuses:
                result = woo_service.sync_orders_to_db(status=status, days=7)
                saved = result.get('total_saved', 0)
                total_saved += saved
                
                if saved > 0:
                    log.info(f"🛒 WooCommerce {status}: {saved} sipariş kaydedildi")
            
            if total_saved > 0:
                log.info(f"🛒 WooCommerce senkronizasyonu tamamlandı: {total_saved} sipariş")
            else:
                log.debug("🛒 WooCommerce: Yeni sipariş yok")
                
        except Exception as e:
            log.error(f"🛒 WooCommerce senkronizasyon hatası: {str(e)}", exc_info=True)


# ── PANEL: Şablon oluştur (form-post)
@gorev_bp.route("/sablon/ekle-ui", methods=["POST"])
@login_required
@admin_required
def sablon_ekle_ui():
    assignee_user_id = request.form.get("assignee_user_id", type=int)
    title = (request.form.get("title") or "").strip()
    due_time = request.form.get("due_time") or "11:00"
    weekdays = ",".join(request.form.getlist("weekdays")) or "0,1,2,3,4"
    priority = int(request.form.get("priority", 2))
    proof_required = bool(request.form.get("proof_required"))
    active = bool(request.form.get("active", True))

    u = User.query.get(assignee_user_id)
    if not u or not title:
        flash("Kullanıcı ve görev adı zorunludur.", "warning")
        return redirect(url_for("gorev.gorev_panel"))

    try:
        h, m = [int(x) for x in (due_time or "11:00").split(":")]
    except Exception:
        h, m = 11, 0

    tpl = TaskTemplate(
        assignee=f"{(u.first_name or '').strip()} {(u.last_name or '').strip()}".strip() or (u.email or "Kullanıcı"),
        assignee_email=u.email,
        title=title,
        due_h=h, due_m=m,
        weekdays=weekdays,
        priority=priority,
        proof_required=proof_required,
        active=active
    )
    db.session.add(tpl); db.session.commit()
    flash("Görev şablonu kaydedildi.", "success")
    return redirect(url_for("gorev.gorev_panel"))


# ── PANEL: Bugüne ekstra görev (form-post)
@gorev_bp.route("/ekstra/ekle-ui", methods=["POST"])
@login_required
@admin_required
def ekstra_ekle_ui():
    assignee_user_id = request.form.get("assignee_user_id", type=int)
    title = (request.form.get("title") or "").strip()
    priority = int(request.form.get("priority", 2))
    proof_required = bool(request.form.get("proof_required"))

    u = User.query.get(assignee_user_id)
    if not u or not title:
        flash("Kullanıcı ve görev adı zorunludur.", "warning")
        return redirect(url_for("gorev.gorev_panel"))

    now_ist = datetime.now(IST)
    today   = now_ist.date()

    task = Task(
        assignee=f"{(u.first_name or '').strip()} {(u.last_name or '').strip()}".strip() or (u.email or "Kullanıcı"),
        assignee_email=u.email,
        title=title,
        date_=today,
        due=now_ist,             # o anki saat
        created_at=now_ist,      # eklenme zamanı (gösterimde bunu kullan)
        priority=priority,
        proof_required=proof_required
    )
    if hasattr(Task, "flexible"):        task.flexible = True
    if hasattr(Task, "expected_window"): task.expected_window = "today"

    db.session.add(task); db.session.commit()
    flash("Bugüne ekstra görev eklendi.", "success")
    return redirect(url_for("gorev.gorev_panel"))
