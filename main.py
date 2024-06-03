from datetime import date
from flask import Flask, abort, render_template, redirect, url_for, flash, request
from flask_bootstrap import Bootstrap5
from flask_ckeditor import CKEditor
from flask_gravatar import Gravatar
from flask_login import UserMixin, login_user, LoginManager, current_user, logout_user
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import relationship, DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Integer, String, Text
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from forms import CreatePostForm, RegisterForm, LoginForm, CommentForm, MessageForm
import os
import smtplib

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get("FLASK_KEY")
ckeditor = CKEditor(app)
Bootstrap5(app)


class Base(DeclarativeBase):
    pass


app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DB_URI")
db = SQLAlchemy(model_class=Base)
db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)

gravatar = Gravatar(app,
                    size=100,
                    rating='g',
                    default='retro',
                    force_default=False,
                    force_lower=False,
                    use_ssl=False,
                    base_url=None)


@login_manager.user_loader
def load_user(user_id):
    return db.get_or_404(User, user_id)


class BlogPost(db.Model):
    __tablename__ = "blog_posts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    author_id: Mapped[int] = mapped_column(Integer, db.ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(250), unique=True, nullable=False)
    subtitle: Mapped[str] = mapped_column(String(250), nullable=False)
    date: Mapped[str] = mapped_column(String(250), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    author = relationship("User", back_populates="posts")
    img_url: Mapped[str] = mapped_column(String(250), nullable=False)
    comments = relationship("Comment", back_populates="parent_post")


class User(db.Model, UserMixin):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(250), unique=True, nullable=False)
    password: Mapped[str] = mapped_column(String(250), nullable=False)
    name: Mapped[str] = mapped_column(String(250), nullable=False)
    posts = relationship("BlogPost", back_populates="author")
    comments = relationship("Comment", back_populates="comment_author")


class Comment(db.Model):
    __tablename__ = "comments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(String(250), nullable=False)
    author_id: Mapped[int] = mapped_column(Integer, db.ForeignKey("users.id"))
    post_id: Mapped[str] = mapped_column(Integer, db.ForeignKey("blog_posts.id"))
    comment_author = relationship("User", back_populates="comments")
    parent_post = relationship("BlogPost", back_populates="comments")


with app.app_context():
    db.create_all()


def admin_only(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.id != 1:
            return abort(403)
        return f(*args, **kwargs)
    return decorated_function


@app.route('/register', methods=["GET", "POST"])
def register():
    register_form = RegisterForm()
    if register_form.validate_on_submit():
        duplicate_user = db.session.execute(db.select(User).where(User.email == register_form.email.data)).scalar()
        if not duplicate_user:
            new_user = User()
            new_user.email = register_form.email.data
            new_user.password = generate_password_hash(password=register_form.password.data, salt_length=8)
            new_user.name = register_form.name.data
            db.session.add(new_user)
            db.session.commit()
            login_user(new_user)
            return redirect(url_for("get_all_posts"))
        else:
            return redirect(url_for("login", flash="An account with that email already exists, please login.", current_user=current_user))
    return render_template("register.html", form=register_form)


@app.route('/login', methods=["GET", "POST"])
def login():
    flash_message = request.args.get("flash")
    if flash_message:
        flash(flash_message)
    login_form = LoginForm()
    if login_form.validate_on_submit():
        email = login_form.email.data
        user = db.session.execute(db.select(User).where(User.email == email)).scalar()
        password = login_form.password.data
        if user:
            if check_password_hash(pwhash=user.password, password=password):
                login_user(user)
                return redirect(url_for("get_all_posts"))
            else:
                flash("Incorrect password used.")
        else:
            flash("That email doesn't exist.")
    return render_template("login.html", form=login_form)


@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('get_all_posts'))


@app.route('/', methods=["GET", "POST"])
def get_all_posts():
    result = db.session.execute(db.select(BlogPost))
    posts = result.scalars().all()
    return render_template("index.html", all_posts=posts)


@app.route("/post/<int:post_id>", methods=["GET", "POST"])
def show_post(post_id):
    comment_form = CommentForm()
    requested_post = db.get_or_404(BlogPost, post_id)

    if comment_form.validate_on_submit():
        if not current_user.is_authenticated:
            return redirect(url_for("login", flash="Please log in to comment."))
        new_comment = Comment(text=comment_form.comment.data,
                              author_id=current_user.id,
                              post_id=requested_post.id)
        db.session.add(new_comment)
        db.session.commit()
    return render_template("post.html", post=requested_post, form=comment_form)


@app.route("/new-post", methods=["GET", "POST"])
@admin_only
def add_new_post():
    form = CreatePostForm()
    if form.validate_on_submit():
        new_post = BlogPost(
            title=form.title.data,
            subtitle=form.subtitle.data,
            body=form.body.data,
            img_url=form.img_url.data,
            author=current_user,
            date=date.today().strftime("%B %d, %Y")
        )
        db.session.add(new_post)
        db.session.commit()
        return redirect(url_for("get_all_posts"))
    return render_template("make-post.html", form=form)


@app.route("/edit-post/<int:post_id>", methods=["GET", "POST"])
@admin_only
def edit_post(post_id):
    post = db.get_or_404(BlogPost, post_id)
    edit_form = CreatePostForm(
        title=post.title,
        subtitle=post.subtitle,
        img_url=post.img_url,
        author=post.author,
        body=post.body
    )
    if edit_form.validate_on_submit():
        post.title = edit_form.title.data
        post.subtitle = edit_form.subtitle.data
        post.img_url = edit_form.img_url.data
        post.author = current_user
        post.body = edit_form.body.data
        db.session.commit()
        return redirect(url_for("show_post", post_id=post.id))
    return render_template("make-post.html", form=edit_form, is_edit=True)


@app.route("/delete/<int:post_id>")
@admin_only
def delete_post(post_id):
    post_to_delete = db.get_or_404(BlogPost, post_id)
    for comment in post_to_delete.comments:
        db.session.delete(comment)
    db.session.delete(post_to_delete)
    db.session.commit()
    return redirect(url_for('get_all_posts'))


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/contact", methods=["GET", "POST"])
def contact():
    form = MessageForm()
    msg_sent = False
    if form.validate_on_submit():
        email = "mypythonproject001@gmail.com"
        password = "spks urom lxsy rwjv"
        with smtplib.SMTP("smtp.gmail.com") as connection:
            connection.starttls()
            connection.login(user=email, password=password)
            connection.sendmail(from_addr=email,
                                to_addrs=email,
                                msg=f"Subject:Form submitted from blog website.\n\n"
                                    f"Name: {form.name.data}\n"
                                    f"Email: {form.email.data}\n"
                                    f"Phone number: {form.phone.data}\n\n"
                                    f"{form.message.data}")
        msg_sent = True
    return render_template("contact.html", form=form, msg_sent=msg_sent)


if __name__ == "__main__":
    app.run(debug=True)
