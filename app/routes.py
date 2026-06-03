import os
import re
import json
import html
from uuid import uuid4
from pathlib import Path
from urllib.parse import quote

import requests
from flask import Blueprint, current_app, render_template, request, redirect, url_for, flash, send_from_directory, jsonify
from sqlalchemy.exc import IntegrityError
from werkzeug.utils import secure_filename

from . import db
from .models import Supporter, SocialSupport, GalleryImage

bp = Blueprint("main", __name__)
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
INSTAGRAM_RE = re.compile(r"^[A-Za-z0-9._]{1,30}$")


def campaign_context():
    return {
        "candidate_name": os.getenv("CANDIDATE_NAME", "Darlon Dutra"),
        "candidate_role": os.getenv("CANDIDATE_ROLE", "Deputado Federal"),
        "campaign_number": os.getenv("CAMPAIGN_NUMBER", "1400"),
        "campaign_cnpj": os.getenv("CAMPAIGN_CNPJ", "00.000.000/0000-00"),
        "legal_notice": os.getenv("LEGAL_NOTICE", "De acordo com a legislação eleitoral vigente."),
        "instagram_url": os.getenv("INSTAGRAM_URL", "https://www.instagram.com/darlondutra/"),
        "parana_pop_url": os.getenv("PARANA_POP_URL", "https://www.paranapop.com.br/"),
        "parana_pop_instagram": os.getenv("PARANA_POP_INSTAGRAM", "https://www.instagram.com/parana.pop/"),
    }


def social_base_count():
    try:
        return max(0, int(os.getenv("SOCIAL_SUPPORT_BASE_COUNT", "4000")))
    except ValueError:
        return 4000


def normalize_instagram(raw_value):
    username = (raw_value or "").strip()
    username = username.replace("https://www.instagram.com/", "")
    username = username.replace("https://instagram.com/", "")
    username = username.split("?")[0].strip("/").lstrip("@")
    return username.lower()


def instagram_headers(username=None):
    referer = "https://www.instagram.com/"
    if username:
        referer = f"https://www.instagram.com/{quote(username)}/"
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": referer,
        "X-IG-App-ID": "936619743392459",
    }


def clean_instagram_image_url(value):
    if not value:
        return None
    value = html.unescape(str(value)).replace("\\/", "/")
    try:
        value = json.loads(f'"{value}"')
    except Exception:
        pass
    return value if value.startswith("http") else None


def find_avatar_url_in_html(page_html):
    patterns = [
        r'"profile_pic_url_hd"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"',
        r'"profile_pic_url"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"',
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, page_html)
        if match:
            avatar = clean_instagram_image_url(match.group(1))
            if avatar:
                return avatar
    return None


def save_avatar_locally(username, avatar_url):
    """Baixa a foto para o volume/upload local para evitar bloqueio de hotlink."""
    if not avatar_url:
        return None

    safe_username = re.sub(r"[^a-z0-9._-]", "", username.lower())[:30] or uuid4().hex
    relative_folder = Path("supporters")
    absolute_folder = Path(current_app.config["UPLOAD_FOLDER"]) / relative_folder
    absolute_folder.mkdir(parents=True, exist_ok=True)

    headers = instagram_headers(username)
    headers.update({"Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"})

    try:
        response = requests.get(avatar_url, headers=headers, timeout=10, stream=True, allow_redirects=True)
        content_type = response.headers.get("Content-Type", "").lower()
        if not response.ok or "image" not in content_type:
            return None

        ext = "jpg"
        if "png" in content_type:
            ext = "png"
        elif "webp" in content_type:
            ext = "webp"

        filename = f"{safe_username}-{uuid4().hex[:8]}.{ext}"
        relative_path = relative_folder / filename
        absolute_path = Path(current_app.config["UPLOAD_FOLDER"]) / relative_path

        with absolute_path.open("wb") as file:
            downloaded = 0
            for chunk in response.iter_content(chunk_size=8192):
                if not chunk:
                    continue
                downloaded += len(chunk)
                if downloaded > 3 * 1024 * 1024:
                    return None
                file.write(chunk)

        if absolute_path.stat().st_size < 300:
            absolute_path.unlink(missing_ok=True)
            return None

        return url_for("main.uploads", filename=str(relative_path).replace("\\", "/"))
    except requests.RequestException:
        return None


def scrape_instagram_avatar(username):
    """Tenta puxar a foto pública do Instagram e salvar localmente.

    É uma raspagem não oficial: pode falhar se o Instagram bloquear, alterar a página
    ou exigir login. Quando falha, o site usa avatar com @ como fallback.
    """
    avatar_url = None

    # 1) Endpoint público usado pelo Instagram Web. Costuma retornar profile_pic_url_hd.
    api_url = f"https://i.instagram.com/api/v1/users/web_profile_info/?username={quote(username)}"
    try:
        response = requests.get(api_url, headers=instagram_headers(username), timeout=8)
        if response.ok:
            payload = response.json()
            user = (payload.get("data") or {}).get("user") or {}
            avatar_url = clean_instagram_image_url(user.get("profile_pic_url_hd") or user.get("profile_pic_url"))
    except (requests.RequestException, ValueError):
        avatar_url = None

    # 2) Fallback: raspa og:image/profile_pic_url do HTML público do perfil.
    if not avatar_url:
        profile_url = f"https://www.instagram.com/{quote(username)}/"
        try:
            response = requests.get(profile_url, headers=instagram_headers(username), timeout=8)
            if response.ok:
                avatar_url = find_avatar_url_in_html(response.text)
        except requests.RequestException:
            avatar_url = None

    # 3) Baixa para o volume local; isso evita a bolinha quebrar por hotlink/referrer.
    local_avatar = save_avatar_locally(username, avatar_url)
    return local_avatar or ""

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@bp.route("/")
def index():
    gallery = GalleryImage.query.order_by(GalleryImage.created_at.desc()).limit(9).all()
    social_supporters = SocialSupport.query.order_by(SocialSupport.created_at.desc()).limit(70).all()
    social_count = social_base_count() + SocialSupport.query.count()
    return render_template(
        "index.html",
        gallery=gallery,
        social_supporters=social_supporters,
        social_count=social_count,
        **campaign_context(),
    )


@bp.route("/apoio", methods=["POST"])
def apoio():
    name = request.form.get("name", "").strip()
    if not name:
        flash("Informe seu nome para registrar o apoio.", "error")
        return redirect(url_for("main.index") + "#apoio")

    supporter = Supporter(
        name=name,
        phone=request.form.get("phone", "").strip(),
        neighborhood=request.form.get("neighborhood", "").strip(),
        message=request.form.get("message", "").strip(),
    )
    db.session.add(supporter)
    db.session.commit()
    flash("Apoio registrado com sucesso. Obrigado por fazer parte dessa caminhada!", "success")
    return redirect(url_for("main.index") + "#apoio")


@bp.route("/api/social-support", methods=["POST"])
def social_support():
    payload = request.get_json(silent=True) or request.form
    username = normalize_instagram(payload.get("instagram"))

    if not username or not INSTAGRAM_RE.match(username):
        return jsonify(ok=False, message="Digite um @ do Instagram válido."), 400

    existing = SocialSupport.query.filter_by(instagram=username).first()
    if existing:
        # Se o registro antigo ficou sem foto, tenta atualizar com a raspagem nova.
        if not existing.avatar_url or not str(existing.avatar_url).startswith("/uploads/"):
            refreshed_avatar = scrape_instagram_avatar(username)
            if refreshed_avatar:
                existing.avatar_url = refreshed_avatar
                db.session.commit()
        return jsonify(
            ok=True,
            already=True,
            message="Esse @ já está no time de apoiadores.",
            supporter={"instagram": existing.instagram, "avatar_url": existing.avatar_url},
            count=social_base_count() + SocialSupport.query.count(),
        )

    avatar_url = scrape_instagram_avatar(username)
    supporter = SocialSupport(instagram=username, avatar_url=avatar_url)
    db.session.add(supporter)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        supporter = SocialSupport.query.filter_by(instagram=username).first()
        return jsonify(
            ok=True,
            already=True,
            message="Esse @ já está no time de apoiadores.",
            supporter={"instagram": supporter.instagram, "avatar_url": supporter.avatar_url},
            count=social_base_count() + SocialSupport.query.count(),
        )

    return jsonify(
        ok=True,
        already=False,
        message="Apoio confirmado. Agora você faz parte desse movimento!",
        supporter={"instagram": supporter.instagram, "avatar_url": supporter.avatar_url},
        count=social_base_count() + SocialSupport.query.count(),
    )


@bp.route("/admin", methods=["GET", "POST"])
def admin():
    admin_password = os.getenv("ADMIN_PASSWORD", "admin")
    authenticated = request.args.get("key") == admin_password or request.form.get("key") == admin_password

    if request.method == "POST" and authenticated:
        file = request.files.get("image")
        title = request.form.get("title", "").strip()
        if not file or file.filename == "":
            flash("Selecione uma imagem.", "error")
        elif not allowed_file(file.filename):
            flash("Formato inválido. Use PNG, JPG, JPEG ou WEBP.", "error")
        else:
            ext = secure_filename(file.filename).rsplit(".", 1)[1].lower()
            filename = f"{uuid4().hex}.{ext}"
            file.save(Path(current_app.config["UPLOAD_FOLDER"]) / filename)
            db.session.add(GalleryImage(filename=filename, title=title))
            db.session.commit()
            flash("Imagem enviada para a galeria.", "success")
        return redirect(url_for("main.admin", key=admin_password))

    supporters = Supporter.query.order_by(Supporter.created_at.desc()).limit(100).all() if authenticated else []
    social_supporters = SocialSupport.query.order_by(SocialSupport.created_at.desc()).limit(150).all() if authenticated else []
    gallery = GalleryImage.query.order_by(GalleryImage.created_at.desc()).all() if authenticated else []
    return render_template(
        "admin.html",
        authenticated=authenticated,
        supporters=supporters,
        social_supporters=social_supporters,
        gallery=gallery,
        **campaign_context(),
    )


@bp.route("/uploads/<path:filename>")
def uploads(filename):
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], filename)


@bp.route("/health")
def health():
    return jsonify(status="ok")
