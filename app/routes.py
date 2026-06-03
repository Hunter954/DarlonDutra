import os
from uuid import uuid4
from pathlib import Path
from flask import Blueprint, current_app, render_template, request, redirect, url_for, flash, send_from_directory, abort, jsonify
from werkzeug.utils import secure_filename
from . import db
from .models import Supporter, GalleryImage

bp = Blueprint("main", __name__)
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}


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


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@bp.route("/")
def index():
    gallery = GalleryImage.query.order_by(GalleryImage.created_at.desc()).limit(9).all()
    return render_template("index.html", gallery=gallery, **campaign_context())


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
    gallery = GalleryImage.query.order_by(GalleryImage.created_at.desc()).all() if authenticated else []
    return render_template("admin.html", authenticated=authenticated, supporters=supporters, gallery=gallery, **campaign_context())


@bp.route("/uploads/<path:filename>")
def uploads(filename):
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], filename)


@bp.route("/health")
def health():
    return jsonify(status="ok")
