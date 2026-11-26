from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, request, session
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from backend.models.users import User
from backend.forms.auth import LoginForm, RegistrationForm, ChangePasswordForm
from backend.extensions import db, limiter
from backend.utils.backup import extract_backup_zip
from backend.utils.reboot import restart_app
from backend.utils.security import is_safe_redirect_target
from werkzeug.utils import secure_filename
from sqlalchemy.exc import IntegrityError
import os, sys, threading, time
from backend.utils import paths
from backend.utils import audit
from backend import features
from backend.features.two_factor import service as two_factor

auth_bp = Blueprint("auth", __name__)


def finish_sign_in(user, remember, next_url):
    """Sign the user in and send them on. Called after the password, or after the
    two-factor code for users who have that on."""
    session.permanent = remember  # True = persistent; False = expires on browser close or app stop
    login_user(user, remember=remember)
    audit.record("auth.signed_in", "user", user.id, user.username)
    if user.force_password_reset:
        flash("You must change your password before continuing.", "warning")
        return redirect(url_for('auth.force_change_password'))
    if is_safe_redirect_target(next_url):
        return redirect(next_url)
    return redirect(url_for('index'))


def _login_username_key():
    """Rate-limit key per username, so guessing one account's password is slowed down
    even when the attempts come from many addresses."""
    return "login-user:" + (request.form.get("username") or "").strip().lower()[:64]


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
@limiter.limit("20 per hour", methods=["POST"], key_func=_login_username_key)
def login():
    # Optional: redirect to register if no users exist
    if User.query.count() == 0:
        # Nobody can log in yet, so drop the "Please log in" flash from the login redirect.
        session.pop("_flashes", None)
        backups = [f for f in os.listdir(paths.BACKUP_DIR) if f.endswith('.zip')]
        show_restore_option = len(backups) > 0
        return render_template('auth/first_run.html', zip_found=show_restore_option, backups=backups)

    form = LoginForm()

    if current_user.is_authenticated and request.method == "GET":
        return redirect(url_for("index"))

    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and user.check_password(form.password.data):
            remember = form.remember.data
            next_url = request.args.get("next", "")
            # With two-factor sign-in on, the password alone signs nobody in: ask for the code.
            if two_factor.begin_sign_in(user, remember, next_url):
                return redirect(url_for("two_factor.verify"))
            return finish_sign_in(user, remember, next_url)
        else:
            audit.record("auth.sign_in_failed", "user", user.id if user else None,
                         (form.username.data or "")[:80], username=(form.username.data or "")[:80])
            flash("Invalid username or password", "danger")

    return render_template("auth/login.html", form=form)

@auth_bp.route("/register", methods=["GET", "POST"])
@limiter.limit("10 per hour", methods=["POST"])
def register():
    # Self-registration exists only to create the very first account (the admin) on a new
    # install. After that, accounts are created by an admin under Users. Any account,
    # including read-only, can read every stored password, so sign-up must never be open.
    if User.query.count() > 0:
        if current_user.is_authenticated:
            return redirect(url_for("index"))
        flash("Sign-up is closed. Ask an administrator to create an account for you.", "warning")
        return redirect(url_for("auth.login"))

    form = RegistrationForm()

    if form.validate_on_submit():
        existing_user = User.query.filter_by(username=form.username.data).first()
        if existing_user:
            flash("Username already exists. Please choose another.", "danger")
            return render_template("auth/register.html", form=form)

        is_first_user = User.query.count() == 0

        user = User(username=form.username.data)
        user.set_password(form.password.data)
        user.role = "admin" if is_first_user else "readonly"

        try:
            db.session.add(user)
            db.session.commit()
            login_user(user)
            flash("Account created and logged in.", "success")
            return redirect(url_for("index"))
        except IntegrityError:
            db.session.rollback()
            flash("A user with this username already exists.", "danger")
        except Exception as e:
            db.session.rollback()
            flash("An unexpected error occurred during registration.", "danger")

    return render_template("auth/register.html", form=form)



@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    audit.record("auth.signed_out", "user", current_user.id, current_user.username)
    logout_user()
    session.clear()
    return redirect(url_for("auth.login"))


@auth_bp.route("/check_username")
@limiter.limit("30 per minute")
def check_username():
    # Tells whether a username exists, so only for the first-run sign-up and for admins
    # creating users. Otherwise anyone could use it to collect valid usernames.
    if User.query.count() > 0 and not (current_user.is_authenticated and current_user.role == "admin"):
        return {"error": "forbidden"}, 403
    username = request.args.get("username", "")
    exists = User.query.filter_by(username=username).first() is not None
    return {"exists": exists}

def _restore_done():
    """After a restore the running workers still hold the old database and encryption key.
    Restart them, and show a page that says so and moves on to the sign-in by itself."""
    audit.record("backup.restored", username="first-run set-up")
    return render_template("auth/restore_done.html", restarting=restart_app())


@auth_bp.route("/first-run", methods=["GET", "POST"])
def first_run():
    user_exists = User.query.first() is not None
    backup_folder = paths.BACKUP_DIR
    zip_files = [f for f in os.listdir(backup_folder) if f.endswith(".zip")]
    zip_found = bool(zip_files)

    if user_exists:
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        action = request.form.get("action")

        if action == "restore" and zip_found:
            try:
                zip_path = os.path.join(backup_folder, zip_files[0])
                ok, message = extract_backup_zip(zip_path)
                if ok:
                    return _restore_done()
                flash(f"Restore failed: {message}", "danger")
                return redirect(url_for("auth.first_run"))
            except Exception as e:
                flash(f"Restore failed: {str(e)}", "danger")
                return redirect(url_for("auth.first_run"))

        elif action == "upload_restore":
            uploaded_file = request.files.get("backup_file")
            if uploaded_file and uploaded_file.filename.endswith(".zip"):
                os.makedirs(backup_folder, exist_ok=True)
                # Never trust the uploaded name: "../../x.zip" would write outside the folder.
                safe_name = secure_filename(uploaded_file.filename) or "uploaded-backup.zip"
                save_path = os.path.join(backup_folder, safe_name)
                uploaded_file.save(save_path)

                try:
                    ok, message = extract_backup_zip(save_path)
                    if not ok:
                        flash(f"Restore failed: {message}", "danger")
                        return redirect(url_for("auth.first_run"))
                    return _restore_done()

                except Exception as e:
                    flash(f"Restore failed: {str(e)}", "danger")
            else:
                flash("Invalid file. Please upload a valid .zip backup.", "danger")

        elif action == "skip":
            return redirect(url_for("auth.register"))

    return render_template("auth/first_run.html", zip_found=zip_found)

@auth_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if current_user.username == "demo":
        flash("The demo account cannot access profile settings.", "warning")
        return redirect(url_for("index"))
    return render_template("auth/profile.html", user=current_user)

@auth_bp.route("/change-password", methods=["POST"])
@login_required
def change_password():
    current_password = request.form.get("current_password")
    new_password = request.form.get("new_password")
    confirm_password = request.form.get("confirm_new_password")

    if not check_password_hash(current_user.password_hash, current_password):
        flash("Current password is incorrect.", "danger")
        return redirect(url_for("auth.profile"))

    if new_password != confirm_password:
        flash("New passwords do not match.", "danger")
        return redirect(url_for("auth.profile"))

    if len(new_password) < 8:
        flash("Password must be at least 8 characters long.", "danger")
        return redirect(url_for("auth.profile"))

    user = current_user._get_current_object()
    user.set_password(new_password)  # also signs out every other session of this user
    db.session.commit()
    login_user(user, remember=session.permanent)
    audit.record("auth.password_changed", "user", user.id, user.username)
    flash("Password updated. Other devices signed in with this account have been signed out.", "success")
    return redirect(url_for("auth.profile"))


@auth_bp.route("/delete-account", methods=["POST"])
@login_required
def delete_account():
    # With no accounts left, the first-run wizard would open again and the next visitor
    # could make themselves admin. So the last admin cannot remove themselves.
    if current_user.role == "admin" and User.query.filter_by(role="admin").count() <= 1:
        flash("You are the only administrator. Make someone else an admin before deleting your account.", "danger")
        return redirect(url_for("auth.profile"))
    user = current_user._get_current_object()
    audit.record("user.deleted", "user", user.id, user.username, detail="Deleted their own account.")
    logout_user()
    session.clear()
    features.emit("user_deleted", user)
    db.session.delete(user)
    db.session.commit()
    flash("Your account has been deleted.", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/force-change-password", methods=["GET", "POST"])
@login_required
def force_change_password():
    if not current_user.force_password_reset:
        return redirect(url_for('index'))

    form = ChangePasswordForm()

    if form.validate_on_submit():
        current_user.set_password(form.new_password.data)
        current_user.force_password_reset = False
        db.session.commit()
        audit.record("auth.password_changed", "user", current_user.id, current_user.username)
        flash("Password updated successfully. Please login again.", "success")
        logout_user()
        return redirect(url_for('auth.login'))

    return render_template("auth/force_change_password.html", form=form)
