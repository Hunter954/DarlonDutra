import os
import re
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


def scrape_instagram_avatar(username):
    """Busca uma imagem pública do perfil de forma simples e com fallback.

    Instagram pode bloquear/alterar a página a qualquer momento. Por isso,
    quando não encontra og:image, usamos um avatar externo por username.
    """
    profile_url = f"https://www.instagram.com/{quote(username)}/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    }
    try:
        response = requests.get(profile_url, headers=headers, timeout=7)
        if response.ok:
            html = response.text
            match = re.search(r'<meta[^>]+property=["\\\']og:image["\\\'][^>]+content=["\\\']([^"\\\']+)', html)
            if not match:
                match = re.search(r'<meta[^>]+content=["\\\']([^"\\\']+)["\\\'][^>]+property=["\\\']og:image["\\\']', html)
            if match:
                avatar = match.group(1).replace("&amp;", "&")
                if avatar.startswith("http"):
                    return avatar
    except requests.RequestException:
        pass

    return f"https://unavatar.io/instagram/{quote(username)}"


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
