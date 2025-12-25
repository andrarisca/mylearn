from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from app import db
from app.models import Course, Module, Lesson
from . import courses_bp
from app.models import Course, Module, Lesson, Enrollment, Progress 

def user_can_access_course(course):
    # Course owner (instructor) can always access
    if current_user.role == "instructor" and current_user.id == course.owner_id:
        return True

    # Otherwise, only enrolled users can access
    existing = Enrollment.query.filter_by(user_id=current_user.id, course_id=course.id).first()
    if existing:
        return True

    return False



@courses_bp.route("/")
@login_required
def list_courses():
    courses = Course.query.order_by(Course.created_at.desc()).all()
    return render_template("courses/list.html", courses=courses)


@courses_bp.route("/create", methods=["GET", "POST"])
@login_required
def create_course():
    # only instructors can create courses
    if current_user.role != "instructor":
        flash("Only instructors can create courses.", "warning")
        return redirect(url_for("courses.list_courses"))

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()

        if not title:
            flash("Title is required.", "danger")
            return redirect(url_for("courses.create_course"))

        course = Course(
            title=title,
            description=description,
            owner_id=current_user.id,
        )
        db.session.add(course)
        db.session.commit()

        flash("Course created successfully.", "success")
        return redirect(url_for("courses.course_detail", course_id=course.id))

    return render_template("courses/create.html")


@courses_bp.route("/<int:course_id>")
@login_required
def course_detail(course_id):
    course = Course.query.get_or_404(course_id)

    # order modules by "order" then id
    modules = sorted(course.modules, key=lambda m: (m.order, m.id))

    # check if current user is enrolled in this course
    is_enrolled = Enrollment.query.filter_by(
        user_id=current_user.id,
        course_id=course.id
    ).first() is not None

    # --- COURSE PROGRESS (beginner-friendly, explicit) ---
    total_lessons = 0
    completed_lessons = 0

    # only show progress if student is enrolled OR user is the instructor/owner
    can_see_progress = is_enrolled or (current_user.role == "instructor" and current_user.id == course.owner_id)

    if can_see_progress:
        for module in modules:
            lessons = sorted(module.lessons, key=lambda l: (l.order, l.id))
            for lesson in lessons:
                total_lessons += 1

                prog = Progress.query.filter_by(
                    user_id=current_user.id,
                    lesson_id=lesson.id
                ).first()

                if prog and prog.status == "completed":
                    completed_lessons += 1

    percent_done = 0
    if total_lessons > 0:
        percent_done = int((completed_lessons / total_lessons) * 100)

    return render_template(
        "courses/detail.html",
        course=course,
        modules=modules,
        is_enrolled=is_enrolled,
        total_lessons=total_lessons,
        completed_lessons=completed_lessons,
        percent_done=percent_done,
        can_see_progress=can_see_progress
    )


@courses_bp.route("/<int:course_id>/enroll", methods=["POST"])
@login_required
def enroll(course_id):
    course = Course.query.get_or_404(course_id)

    # instructors don't need enrollment for their own course
    if current_user.role == "instructor" and current_user.id == course.owner_id:
        flash("You already own this course.", "info")
        return redirect(url_for("courses.course_detail", course_id=course.id))

    existing = Enrollment.query.filter_by(
        user_id=current_user.id,
        course_id=course.id
    ).first()

    if existing:
        flash("You are already enrolled in this course.", "info")
        return redirect(url_for("courses.course_detail", course_id=course.id))

    enrollment = Enrollment(user_id=current_user.id, course_id=course.id)
    db.session.add(enrollment)
    db.session.commit()

    flash("Enrolled successfully!", "success")
    return redirect(url_for("courses.course_detail", course_id=course.id))


@courses_bp.route("/<int:course_id>/unenroll", methods=["POST"])
@login_required
def unenroll(course_id):
    course = Course.query.get_or_404(course_id)

    enrollment = Enrollment.query.filter_by(
        user_id=current_user.id,
        course_id=course.id
    ).first()

    if not enrollment:
        flash("You are not enrolled in this course.", "warning")
        return redirect(url_for("courses.course_detail", course_id=course.id))

    db.session.delete(enrollment)
    db.session.commit()

    flash("You have unenrolled.", "success")
    return redirect(url_for("courses.course_detail", course_id=course.id))



@courses_bp.route("/<int:course_id>/add-module", methods=["GET", "POST"])
@login_required
def add_module(course_id):
    course = Course.query.get_or_404(course_id)

    # only the instructor who owns the course can add modules
    if current_user.role != "instructor" or current_user.id != course.owner_id:
        flash("Only the course instructor can add modules.", "warning")
        return redirect(url_for("courses.course_detail", course_id=course.id))

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        order_raw = request.form.get("order", "").strip()

        if not title:
            flash("Module title is required.", "danger")
            return redirect(url_for("courses.add_module", course_id=course.id))

        try:
            order = int(order_raw) if order_raw else 0
        except ValueError:
            order = 0

        module = Module(
            title=title,
            course_id=course.id,
            order=order,
        )
        db.session.add(module)
        db.session.commit()

        flash("Module added successfully.", "success")
        return redirect(url_for("courses.course_detail", course_id=course.id))

    return render_template("courses/add_module.html", course=course)

@courses_bp.route("/<int:course_id>/modules/<int:module_id>")
@login_required
def module_detail(course_id, module_id):
    course = Course.query.get_or_404(course_id)
    module = Module.query.get_or_404(module_id)

    # make sure module belongs to course
    if module.course_id != course.id:
        flash("Invalid module.", "danger")
        return redirect(url_for("courses.course_detail", course_id=course.id))

    # ACCESS CHECK
    if not user_can_access_course(course):
        flash("Please enroll to access the modules and lessons.", "warning")
        return redirect(url_for("courses.course_detail", course_id=course.id))

    lessons = sorted(module.lessons, key=lambda l: (l.order, l.id))

    # progress counts for current user
    total_lessons = len(lessons)

    completed_lessons = 0
    for lesson in lessons:
        prog = Progress.query.filter_by(user_id=current_user.id, lesson_id=lesson.id).first()
        if prog and prog.status == "completed":
            completed_lessons += 1

    percent_done = 0
    if total_lessons > 0:
        percent_done = int((completed_lessons / total_lessons) * 100)

    return render_template(
    "courses/module_detail.html",
    course=course,
    module=module,
    lessons=lessons,
    total_lessons=total_lessons,
    completed_lessons=completed_lessons,
    percent_done=percent_done,
    module_completed=(total_lessons > 0 and completed_lessons == total_lessons)
)


@courses_bp.route("/<int:course_id>/modules/<int:module_id>/add-lesson", methods=["GET", "POST"])
@login_required
def add_lesson(course_id, module_id):
    module = Module.query.get_or_404(module_id)
    course = Course.query.get_or_404(course_id)

    # Only instructor who owns the course can add lessons
    if current_user.role != "instructor" or course.owner_id != current_user.id:
        flash("Only the course instructor can add lessons.", "danger")
        return redirect(
            url_for("courses.module_detail", course_id=course.id, module_id=module.id)
        )

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        content = request.form.get("content", "").strip()
        order_raw = request.form.get("order", "").strip()

        if not title:
            flash("Lesson title is required.", "danger")
            return redirect(
                url_for("courses.add_lesson", course_id=course.id, module_id=module.id)
            )

        try:
            order = int(order_raw) if order_raw else 0
        except ValueError:
            order = 0

        lesson = Lesson(
            title=title,
            content=content,
            order=order,
            module_id=module.id,
        )

        db.session.add(lesson)
        db.session.commit()

        flash("Lesson added successfully!", "success")
        return redirect(
            url_for("courses.module_detail", course_id=course.id, module_id=module.id)
        )

    return render_template("courses/add_lesson.html", course=course, module=module)

@courses_bp.route("/<int:course_id>/modules/<int:module_id>/lessons/<int:lesson_id>")
@login_required
def lesson_detail(course_id, module_id, lesson_id):
    course = Course.query.get_or_404(course_id)
    module = Module.query.get_or_404(module_id)

    if module.course_id != course.id:
        flash("Invalid module.", "danger")
        return redirect(url_for("courses.course_detail", course_id=course.id))

    # ACCESS CHECK
    if not user_can_access_course(course):
        flash("Please enroll to access lessons.", "warning")
        return redirect(url_for("courses.course_detail", course_id=course.id))

    # get lesson safely (important!)
    lesson = Lesson.query.filter_by(id=lesson_id, module_id=module.id).first()
    if not lesson:
        flash("Invalid lesson.", "danger")
        return redirect(url_for("courses.module_detail", course_id=course.id, module_id=module.id))

    return render_template(
        "courses/lesson_detail.html",
        course=course,
        module=module,
        lesson=lesson
    )


@courses_bp.route("/<int:course_id>/modules/<int:module_id>/lessons/<int:lesson_id>/complete")
@login_required
def complete_lesson(course_id, module_id, lesson_id):
    from app.models import Progress

    lesson = Lesson.query.get_or_404(lesson_id)

    # ensure lesson belongs to module & course
    if lesson.module_id != module_id:
        flash("Invalid lesson.", "danger")
        return redirect(url_for("courses.module_detail",
                                course_id=course_id,
                                module_id=module_id))

    # find existing progress record
    progress = Progress.query.filter_by(
        user_id=current_user.id,
        lesson_id=lesson_id
    ).first()

    if not progress:
        progress = Progress(
            user_id=current_user.id,
            lesson_id=lesson_id,
            status="completed"
        )
        db.session.add(progress)
    else:
        progress.status = "completed"

    db.session.commit()

    flash("Lesson marked as completed!", "success")
    return redirect(url_for("courses.lesson_detail",
                            course_id=course_id,
                            module_id=module_id,
                            lesson_id=lesson_id))
