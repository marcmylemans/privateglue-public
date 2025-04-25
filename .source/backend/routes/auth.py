from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, request, session
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from backend.models.users import User
from backend.forms.auth import LoginForm, RegistrationForm, ChangePasswordForm
from backend.extensions import db
from backend.utils.backup import extract_backup_zip
from backend.utils.reboot import shutdown_server
import os, sys, threading, time

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    # Optional: redirect to register if no users exist
    if User.query.count() == 0:
        backups = [f for f in os.listdir('/app/backups') if f.endswith('.zip')]
        show_restore_option = len(backups) > 0
        return render_template('auth/first_run.html', show_restore_option=show_restore_option, backups=backups)

    form = LoginForm()

    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and user.check_password(form.password.data):
            remember = form.remember.data
            session.permanent = remember  # True = persistent; False = expires on browser close or app stop
            login_user(user, remember=remember)
            if user.force_password_reset:
                flash("You must change your password before continuing.", "warning")
                return redirect(url_for('auth.force_change_password'))
            else:
                return redirect(url_for('index'))
        else:
            flash("Invalid username or password", "danger")

    return render_template("auth/login.html", form=form)

@auth_bp.route("/register", methods=["GET", "POST"])
def register():
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



@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("index"))


@auth_bp.route("/check_username")
def check_username():
    from backend.models.users import User  # or your adjusted import
    username = request.args.get("username", "")
    exists = User.query.filter_by(username=username).first() is not None
    return {"exists": exists}

@auth_bp.route("/first-run", methods=["GET", "POST"])
def first_run():
    user_exists = User.query.first() is not None
    backup_folder = "/app/backups"
    zip_files = [f for f in os.listdir(backup_folder) if f.endswith(".zip")]
    zip_found = bool(zip_files)

    if user_exists:
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        action = request.form.get("action")

        if action == "restore" and zip_found:
            try:
                zip_path = os.path.join(backup_folder, zip_files[0])
                extract_backup_zip(zip_path)
                flash("Backup successfully restored. Please restart the app.", "success")
                return redirect(url_for("auth.login"))
            except Exception as e:
                flash(f"Restore failed: {str(e)}", "danger")
                return redirect(url_for("auth.first_run"))

        elif action == "upload_restore":
            uploaded_file = request.files.get("backup_file")
            if uploaded_file and uploaded_file.filename.endswith(".zip"):
                os.makedirs(backup_folder, exist_ok=True)
                save_path = os.path.join(backup_folder, uploaded_file.filename)
                uploaded_file.save(save_path)

                try:
                    extract_backup_zip(save_path)
                    shutdown_func = request.environ.get("werkzeug.server.shutdown")

                    if shutdown_func:
                        threading.Thread(target=lambda: (time.sleep(1), shutdown_server(shutdown_func))).start()
                        flash("Backup restored. Shutting down to apply restore...", "warning")
                        return redirect(url_for("auth.login"))
                    else:
                        flash("Backup restored. Please restart the app manually.", "warning")
                        return redirect(url_for("auth.login"))
                    
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

    current_user.set_password(new_password)
    db.session.commit()
    flash("Password updated successfully.", "success")
    return redirect(url_for("auth.profile"))


@auth_bp.route("/delete-account", methods=["POST"])
@login_required
def delete_account():
    user_id = current_user.id
    db.session.delete(current_user)
    db.session.commit()
    flash("Your account has been deleted.", "info")
    return redirect(url_for("auth.logout"))


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
        flash("Password updated successfully. Please login again.", "success")
        logout_user()
        return redirect(url_for('auth.login'))

    return render_template("auth/force_change_password.html", form=form)
