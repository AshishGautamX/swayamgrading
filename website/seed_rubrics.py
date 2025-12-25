# seed_rubrics.py
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from .models import Assignment, Submission, db, Class, RubricCriteria, Rubric
import re


def seed_rubrics():
    rubric_data = [...]  # Your pandas data

    for entry in rubric_data:
        criteria = RubricCriteria(
            level=entry[0],
            category=entry[1],
            rating=entry[2],
            score=entry[3],
            description=entry[4]
        )
        db.session.add(criteria)
    db.session.commit()