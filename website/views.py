from dotenv import load_dotenv
import tempfile
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash, session
from flask_login import login_required, current_user
from .models import Assignment, Submission, db, Class, Rubric, RubricCriteria, User, GoogleClass, GradingJob, check_resource_access
from huggingface_hub import InferenceClient
import re, json, os
import urllib.parse
import google.oauth2.credentials
import google_auth_oauthlib.flow
import googleapiclient.discovery
import google.cloud
from threading import Thread


SCOPES = [
    'https://www.googleapis.com/auth/classroom.courses.readonly',
    'https://www.googleapis.com/auth/classroom.coursework.me',
    'https://www.googleapis.com/auth/classroom.coursework.students',
    'https://www.googleapis.com/auth/classroom.rosters.readonly',
    'https://www.googleapis.com/auth/userinfo.profile',
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/drive.readonly',
    'openid'
]

load_dotenv()

API_KEY = os.getenv("HUGGINGFACE_API_KEY")

views = Blueprint('views', __name__)

# Configure Hugging Face Inference API with new router endpoint
client = InferenceClient(token=API_KEY, base_url="https://router.huggingface.co")
MODEL_NAME = "meta-llama/Llama-3.3-70B-Instruct"


def extract_grade(text):
    """
    Extract a numerical grade from the AI response.
    Looks for patterns like "Grade: 85/100" or "Score: 90".
    """
    # Regex to find grades in the format XX/100 or XX%
    grade_pattern = r'\b(\d{1,3})\s*/\s*100\b|\b(\d{1,3})\s*%\b|\b(\d{1,3})\b'
    matches = re.findall(grade_pattern, text)
    
    if matches:
        # Flatten the tuple and filter out empty strings
        numbers = [num for group in matches for num in group if num]
        if numbers:
            return float(numbers[0])  # Return the first valid number found
    return None  # Return None if no grade is found

@views.route('/')
def home():
    """
    Homepage route.
    Redirects to dashboard if user is authenticated, otherwise shows landing page.
    """
    if current_user.is_authenticated:
        return redirect(url_for('views.dashboard'))
    return render_template('home.html')

@views.route('/dashboard')
@login_required
def dashboard():
    # Get both user-created rubrics and system-created default rubrics (limit to 3 for preview)
    rubrics = Rubric.query.filter(
        (Rubric.creator_id == current_user.id) | (Rubric.creator_id == None)
    ).limit(3).all()
    return render_template('dashboard.html', 
                         user=current_user, 
                         classes=current_user.classes,
                         rubrics=rubrics)


# website/views.py
@views.route('/create-class', methods=['GET', 'POST'])
@login_required
def create_class():
    if request.method == 'POST':
        try:
            # Get form data
            class_name = request.form.get('class_name')
            assignment_name = request.form.get('assignment_name')
            question = request.form.get('question')
            level = request.form.get('level')
            rubric_id = request.form.get('rubric_id')
            
            # Validate required fields
            if not class_name or not assignment_name or not question or not level or not rubric_id:
                flash('All fields are required!', category='error')
                return redirect(url_for('views.create_class'))

            # Create new class
            new_class = Class(
                name=class_name,
                level=level,
                owner_id=current_user.id
            )
            db.session.add(new_class)
            db.session.commit()

            # Create default assignment
            new_assignment = Assignment(
                name=assignment_name,
                question=question,
                rubric_id=rubric_id,
                class_id=new_class.id
            )
            db.session.add(new_assignment)
            db.session.commit()

            flash('Class created successfully!', category='success')
            return redirect(url_for('views.view_class', class_id=new_class.id))

        except Exception as e:
            db.session.rollback()
            flash('Error creating class: ' + str(e), category='error')
            return redirect(url_for('views.create_class'))

    # If GET request, fetch rubrics and render the form
    rubrics = Rubric.query.all()
    return render_template('create_class.html', user=current_user, form={}, rubrics=rubrics)

@views.route('/class/<int:class_id>')
@login_required
def view_class(class_id):
    cls = Class.query.options(
        db.joinedload(Class.assignments).joinedload(Assignment.submissions)
    ).get_or_404(class_id)
    return render_template("class.html", user=current_user, cls=cls, assignments=cls.assignments)

@views.route('/delete-class/<int:class_id>', methods=['POST'])
@login_required
def delete_class(class_id):
    try:
        # Fetch the class
        cls = Class.query.get_or_404(class_id)
        
        # Check if the current user is the owner of the class
        if cls.owner_id != current_user.id:
            flash('You do not have permission to delete this class!', category='error')
            return redirect(url_for('views.dashboard'))
            
        # Delete associated assignments and their submissions
        for assignment in cls.assignments:
            # Delete all submissions for this assignment
            Submission.query.filter_by(assignment_id=assignment.id).delete()
            
        # Delete all assignments for this class
        Assignment.query.filter_by(class_id=class_id).delete()
            
        # Delete the class
        db.session.delete(cls)
        db.session.commit()
        
        flash('Class deleted successfully!', category='success')
        return redirect(url_for('views.dashboard'))
        
    except Exception as e:
        db.session.rollback()
        flash('Error deleting class: ' + str(e), category='error')
        return redirect(url_for('views.dashboard'))


@views.route('/extract-pdf-text', methods=['POST'])
@login_required
def extract_pdf_text():
    """
    Extract text from uploaded PDF files using PyPDF2.
    """
    try:
        from PyPDF2 import PdfReader
        import io
        
        if 'pdf_file' not in request.files:
            return jsonify({'error': 'No PDF file provided'}), 400
        
        pdf_file = request.files['pdf_file']
        
        if pdf_file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not pdf_file.filename.lower().endswith('.pdf'):
            return jsonify({'error': 'File must be a PDF'}), 400
        
        # Read PDF file
        pdf_bytes = pdf_file.read()
        pdf_stream = io.BytesIO(pdf_bytes)
        
        # Extract text using PyPDF2
        pdf_reader = PdfReader(pdf_stream)
        extracted_text = ''
        
        for page_num, page in enumerate(pdf_reader.pages):
            try:
                page_text = page.extract_text()
                if page_text:
                    extracted_text += page_text + '\n\n'
            except Exception as e:
                print(f"Error extracting text from page {page_num + 1}: {str(e)}")
                continue
        
        if not extracted_text.strip():
            return jsonify({'error': 'No text could be extracted from the PDF'}), 400
        
        return jsonify({
            'success': True,
            'text': extracted_text.strip(),
            'pages': len(pdf_reader.pages)
        })
    
    except Exception as e:
        print(f"PDF extraction error: {str(e)}")
        return jsonify({'error': f'Failed to extract text: {str(e)}'}), 500


@views.route('/grade', methods=['POST'])
@login_required
def grade_assignment():
    """
    API endpoint for grading assignments using AI with full rubric support.
    """
    data = request.json
    question = data.get("question")
    student_answer = data.get("student_answer")
    rubric_id = data.get("rubric_id")
    
    # Validate input
    if not question or not student_answer:
        return jsonify({'error': 'Missing required fields'}), 400
    
    # Get rubric if provided
    rubric_criteria = []
    level = "High School"  # Default level
    if rubric_id:
        rubric = Rubric.query.get(rubric_id)
        if rubric:
            rubric_criteria = rubric.get_criteria()
            level = rubric.level
    
    # Construct the grading prompt with rubric
    prompt = f"""
    You are an AI teaching assistant. Grade this student answer based on the provided rubric:
    
    Question: {question}
    Student Answer: {student_answer}
    
    Rubric Criteria for {level} Level:
    {json.dumps(rubric_criteria, indent=2) if rubric_criteria else "No specific rubric provided"}
    
    Provide detailed feedback and a numerical grade between 0-100.
    Format your response as a JSON object with the following keys:
    - feedback: [detailed feedback]
    - grade: [numerical grade as a string in format "X/100"]
    - summary: [brief summary of the feedback]
    - glow: [what the student did well]
    - grow: [areas for improvement]
    - think_about_it: [questions to ponder for improvement]
    - rubric: [detailed rubric breakdown with scores and explanations]
    
    IMPORTANT GRADING INSTRUCTIONS:
    1. If the student's answer is completely unrelated to the question, assign 0 marks and provide appropriate feedback.
    2. If the content appears to be AI-generated, deduct marks appropriately and mention this concern in your feedback.
    3. Return ONLY the JSON object with no markdown formatting, no backticks, and no code blocks.
    
    Your entire response must be a valid JSON object that can be directly parsed.
    """
    
    try:
        # Get AI response from Hugging Face
        response = client.chat_completion(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2000,
            temperature=0.7
        )
        response_text = response.choices[0].message.content
        
        # Process the response to extract clean JSON
        processed_text = clean_ai_response(response_text)
        
        try:
            feedback_data = json.loads(processed_text)
            
            # Ensure grade is properly formatted
            if isinstance(feedback_data.get('grade'), str):
                if '/' not in feedback_data['grade']:
                    feedback_data['grade'] = f"{feedback_data['grade']}/100"
            elif isinstance(feedback_data.get('grade'), (int, float)):
                feedback_data['grade'] = f"{feedback_data['grade']}/100"
            
            # Ensure all expected keys are present
            required_keys = ['feedback', 'grade', 'summary', 'glow', 'grow', 'think_about_it', 'rubric']
            for key in required_keys:
                if key not in feedback_data:
                    feedback_data[key] = {"rubric": {"Overall": "Assessment included in general feedback."}}[key] if key == 'rubric' else "Not provided in AI response."
            
            return jsonify(feedback_data)
            
        except json.JSONDecodeError as e:
            print(f"JSON parse error: {str(e)}")
            print(f"Attempted to parse: {processed_text}")
            
            # Fallback to basic response
            feedback_data = {
                'feedback': response_text,
                'grade': extract_grade(response_text) or "70/100",
                'summary': "AI provided feedback but not in the expected format.",
                'glow': extract_section(response_text, "glow", "positive points", "strengths"),
                'grow': extract_section(response_text, "grow", "improve", "weaknesses"),
                'think_about_it': extract_section(response_text, "think", "consider", "reflect"),
                'rubric': {"Overall": "See feedback for assessment details."}
            }
            return jsonify(feedback_data)
    
    except Exception as e:
        print(f"Error in grade_assignment: {str(e)}")
        return jsonify({'error': str(e)}), 500
    
    # website/views.py

# website/views.py

@views.route('/add-submission/<int:assignment_id>', methods=['GET', 'POST'])
@login_required
def add_submission(assignment_id):
    assignment = Assignment.query.get_or_404(assignment_id)
    
    if request.method == 'POST':
        student_name = request.form.get('student_name')
        student_email = request.form.get('student_email')
        student_answer = request.form.get('student_answer')
        
        if not student_name or not student_email or not student_answer:
            flash('Student name, email, and answer are required!', category='error')
            return redirect(url_for('views.view_class', class_id=assignment.class_id))
        
        # Create new submission
        new_submission = Submission(
            student_name=student_name,
            student_email=student_email,
            student_answer=student_answer,
            assignment_id=assignment.id,
            student_id=current_user.id  # Assuming the teacher is submitting on behalf of the student
        )
        
        db.session.add(new_submission)
        db.session.commit()
        
        flash('Submission added successfully!', category='success')
        return redirect(url_for('views.view_class', class_id=assignment.class_id))
    
    # If GET request, render the form dialog
    return render_template('add_submission.html', assignment=assignment)

# website/views.py

@views.route('/create-assignment/<int:class_id>', methods=['GET', 'POST'])
@login_required
def create_assignment(class_id):
    cls = Class.query.get_or_404(class_id)
    
    if request.method == 'POST':
        name = request.form.get('name')
        question = request.form.get('question')
        rubric_id = request.form.get('rubric_id')
        
        if not name or not question:
            flash('Assignment name and question are required!', category='error')
            return redirect(url_for('views.create_assignment', class_id=class_id))
        
        # Create new assignment
        new_assignment = Assignment(
            name=name,
            question=question,
            rubric_id=rubric_id,
            class_id=class_id
        )
        
        db.session.add(new_assignment)
        db.session.commit()
        
        flash('Assignment created successfully!', category='success')
        return redirect(url_for('views.view_class', class_id=class_id))
    
    # If GET request, render the form with rubrics
    rubrics = Rubric.query.filter(
        (Rubric.creator_id == current_user.id) | (Rubric.creator_id == None)
    ).all()
    return render_template('create_assignment.html', cls=cls, rubrics=rubrics)


@views.route('/create-rubric', methods=['GET', 'POST'])
@login_required
def create_rubric():
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        level = request.form.get('level')  # Primary, Middle School, High School

        if not name or not level:
            flash('Name and level are required!', category='error')
            return redirect(url_for('views.create_rubric'))

        # Automatically populate criteria based on level
        criteria_data = RubricCriteria.query.filter_by(level=level).all()
        criteria = [{
            'category': c.category,
            'rating': c.rating,
            'score': c.score,
            'description': c.description
        } for c in criteria_data]

        # Create new rubric
        new_rubric = Rubric(
            name=name,
            description=description,
            level=level,
            criteria=json.dumps(criteria),  # Store criteria as JSON
            creator_id=current_user.id
        )

        db.session.add(new_rubric)
        db.session.commit()

        return jsonify({'success': True, 'message': 'Rubric created!'})

    # If GET request, render the form
    return render_template('rubric_form.html')


@views.route('/delete-assignment/<int:assignment_id>')
@login_required
def delete_assignment(assignment_id):
    assignment = Assignment.query.get_or_404(assignment_id)
    class_id = assignment.class_id
    
    # Check if the current user has permission to delete this assignment
    # Assuming the user can only delete assignments from their own classes
    cls = Class.query.get_or_404(class_id)
    if cls not in current_user.classes:
        flash('You do not have permission to delete this assignment!', category='error')
        return redirect(url_for('views.view_class', class_id=class_id))
    
    try:
        # Delete all grading jobs related to this assignment first
        GradingJob.query.filter_by(assignment_id=assignment_id).delete()
        
        # Delete all submissions related to this assignment
        for submission in assignment.submissions:
            db.session.delete(submission)
        
        # Then delete the assignment
        db.session.delete(assignment)
        db.session.commit()
        
        flash('Assignment deleted successfully!', category='success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting assignment: {str(e)}', category='error')
    
    return redirect(url_for('views.view_class', class_id=class_id))


@views.route('/delete-submission/<int:submission_id>')
@login_required
def delete_submission(submission_id):
    submission = Submission.query.get_or_404(submission_id)
    assignment = Assignment.query.get_or_404(submission.assignment_id)
    class_id = assignment.class_id
    
    # Check if the current user has permission to delete this submission
    # Assuming the user can only delete submissions from their own classes
    cls = Class.query.get_or_404(class_id)
    if cls not in current_user.classes:
        flash('You do not have permission to delete this submission!', category='error')
        return redirect(url_for('views.view_class', class_id=class_id))
    
    db.session.delete(submission)
    db.session.commit()
    
    flash('Submission deleted successfully!', category='success')
    return redirect(url_for('views.view_class', class_id=class_id))

@views.route('/rubrics')
@login_required
def view_rubrics():
    # Get both user-created rubrics and system-created default rubrics
    rubrics = Rubric.query.filter(
        (Rubric.creator_id == current_user.id) | (Rubric.creator_id == None)
    ).all()
    return render_template('rubrics.html', rubrics=rubrics)

    

@views.route('/grade-submission/<int:submission_id>', methods=['GET', 'POST'])
@login_required
def deepgrade(submission_id):
    """
    View for grading a specific submission using AI.
    """
    try:
        # Get the submission
        submission = Submission.query.get_or_404(submission_id)
        assignment = submission.assignment_ref
        class_obj = assignment.class_ref
        
        if not check_resource_access(class_obj):
            flash("You do not have permission to grade this submission", "error")
            return redirect(url_for('views.dashboard'))
        
        rubric = assignment.rubric

        if not rubric:
            flash('No rubric assigned to this assignment!', 'error')
            return redirect(url_for('views.view_class', class_id=assignment.class_id))

        # Handle POST request (AJAX call for grading)
        if request.method == 'POST':
            try:
                # Fetch level-specific rubric criteria
                rubric_criteria = rubric.get_criteria()

                # Construct the grading prompt with rubric criteria
                prompt = f"""
                You are an AI teaching assistant. Grade this student answer based on the provided rubric:
                
                Question: {assignment.question}
                Student Answer: {submission.student_answer}
                
                Rubric Criteria for {rubric.level} Level:
                {json.dumps(rubric_criteria, indent=2)}
                
                Provide detailed feedback and a numerical grade between 0-100.
                Format your response as a JSON object with the following keys:
                - feedback: [detailed feedback]
                - grade: [numerical grade as a string in format "X/100"]
                - summary: [brief summary of the feedback]
                - glow: [what the student did well]
                - grow: [areas for improvement]
                - think_about_it: [questions to ponder for improvement]
                - rubric: [detailed rubric breakdown with scores and explanations]
                
                IMPORTANT GRADING INSTRUCTIONS:
                1. If the student's answer is completely unrelated to the question, assign 0 marks and provide appropriate feedback.
                2. If the content appears to be AI-generated, deduct marks appropriately and mention this concern in your feedback.
                3. Return ONLY the JSON object with no markdown formatting, no backticks, and no code blocks.
                
                Your entire response must be a valid JSON object that can be directly parsed.
                """

                try:
                    # Get AI response from Hugging Face
                    response = client.chat_completion(
                        model=MODEL_NAME,
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=2000,
                        temperature=0.7
                    )
                    response_text = response.choices[0].message.content
                    print("AI Response:", response_text)  # Log the AI response

                    # Process the response to extract clean JSON
                    processed_text = clean_ai_response(response_text)
                    print("Processed Text:", processed_text)  # Debug output

                    try:
                        feedback_data = json.loads(processed_text)

                        # Ensure grade is properly formatted
                        if isinstance(feedback_data.get('grade'), str):
                            if '/' not in feedback_data['grade']:
                                feedback_data['grade'] = f"{feedback_data['grade']}/100"
                        elif isinstance(feedback_data.get('grade'), (int, float)):
                            feedback_data['grade'] = f"{feedback_data['grade']}/100"

                        # Ensure all expected keys are present
                        required_keys = ['feedback', 'grade', 'summary', 'glow', 'grow', 'think_about_it', 'rubric']
                        for key in required_keys:
                            if key not in feedback_data:
                                feedback_data[key] = {"rubric": {"Overall": "Assessment included in general feedback."}}[key] if key == 'rubric' else "Not provided in AI response."

                    except json.JSONDecodeError as e:
                        print(f"JSON parse error: {str(e)}")
                        print(f"Attempted to parse: {processed_text}")

                        feedback_data = {
                            'feedback': response_text,
                            'grade': extract_grade(response_text) or "70/100",
                            'summary': "AI provided feedback but not in the expected format.",
                            'glow': extract_section(response_text, "glow", "positive points", "strengths"),
                            'grow': extract_section(response_text, "grow", "improve", "weaknesses"),
                            'think_about_it': extract_section(response_text, "think", "consider", "reflect"),
                            'rubric': {"Overall": "See feedback for assessment details."}
                        }

                    # Save feedback and grade to submission
                    submission.ai_feedback = json.dumps(feedback_data)

                    # Extract numerical grade
                    grade_value = 0
                    try:
                        if isinstance(feedback_data['grade'], str) and '/' in feedback_data['grade']:
                            grade_value = float(feedback_data['grade'].split('/')[0])
                        elif isinstance(feedback_data['grade'], (int, float)):
                            grade_value = float(feedback_data['grade'])
                    except (KeyError, ValueError, TypeError):
                        extracted = extract_grade(response_text)
                        grade_value = extracted if extracted is not None else 70

                    submission.grade = grade_value
                    db.session.commit()

                    print("Final feedback data:", json.dumps(feedback_data))  # Debug logging
                    return jsonify(feedback_data)

                except Exception as e:
                    print(f"Error processing AI response: {str(e)}")
                    print(f"Error processing AI response: {str(e)}")

                    fallback_data = {
                        'feedback': "The AI grading system encountered an error. Please try again or grade manually.",
                        'grade': "70/100",
                        'summary': "Automatic grading encountered an error.",
                        'glow': "Unable to evaluate strengths due to system error.",
                        'grow': "Unable to evaluate areas for improvement due to system error.",
                        'think_about_it': "How might the system be improved to better evaluate this response?",
                        'rubric': {"Overall": "System error prevented detailed evaluation."}
                    }

                    submission.ai_feedback = json.dumps(fallback_data)
                    submission.grade = 70
                    db.session.commit()

                    return jsonify(fallback_data)

            except Exception as e:
                print(f"Error in deepgrade route: {str(e)}")
                print(f"Error in deepgrade POST request: {str(e)}")
                return jsonify({'error': str(e)}), 500

        # Handle GET request (render the template)
        try:
            ai_feedback = json.loads(submission.ai_feedback) if submission.ai_feedback else None
        except (json.JSONDecodeError, TypeError) as e:
            print(f"Invalid JSON in ai_feedback: {str(e)}. Falling back to raw text.")
            print(f"Invalid JSON in ai_feedback for submission {submission_id}: {str(e)}")
            ai_feedback = submission.ai_feedback

        grade = submission.grade if submission.grade is not None else 0

        return render_template('deepgrade.html',
                            submission=submission,
                            assignment=assignment,
                            rubric=rubric,
                            ai_feedback=ai_feedback,
                            grade=grade)
                            
    except Exception as e:
        # Global error handling for the entire route
        print(f"Global error in deepgrade route: {str(e)}")
        print(f"Global error in deepgrade route for submission {submission_id}: {str(e)}")
        flash(f"An error occurred while accessing the submission: {str(e)}", "error")
        # Redirect to a safe page
        return redirect(url_for('views.dashboard'))


def clean_ai_response(text):
    """
    Clean the AI response to extract valid JSON.
    Removes markdown code blocks, backticks, and other non-JSON content.
    """
    import re
    import json
    
    print(f"DEBUG - clean_ai_response input: {text[:100]}...")
    
    if not text:
        print("DEBUG - Empty text received in clean_ai_response")
        return "{}"
    
    # Remove markdown code blocks and backticks
    cleaned_text = re.sub(r'```json\s*|\s*```|`', '', text.strip())
    print(f"DEBUG - After removing markdown: {cleaned_text[:100]}...")
    
    # Try to extract a JSON object if there's text before or after the JSON
    json_pattern = re.compile(r'(\{.*\})', re.DOTALL)
    match = json_pattern.search(cleaned_text)
    if match:
        potential_json = match.group(1)
        # Verify it's valid JSON with a quick test before returning
        try:
            json.loads(potential_json)
            print("DEBUG - Successfully extracted and validated JSON object")
            return potential_json
        except json.JSONDecodeError as e:
            print(f"DEBUG - JSON extraction failed: {e}")
            # If we can't parse the extracted content as JSON, fall back to the cleaned text
            pass
    
    # Check if the cleaned text itself might be valid JSON
    try:
        json.loads(cleaned_text)
        print("DEBUG - Cleaned text is valid JSON")
        return cleaned_text
    except json.JSONDecodeError as e:
        print(f"DEBUG - Cleaned text is not valid JSON: {e}")
        # If we still can't parse it, let's try to convert it to a JSON-like structure
        # This is a fallback for cases where the AI returns structured text but not valid JSON
        try:
            result = {}
            current_key = None
            lines = cleaned_text.split('\n')
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                    
                # Look for key-value patterns like "Feedback: This is feedback"
                kv_match = re.match(r'^(feedback|grade|summary|glow|grow|think_about_it|rubric):(.*)$', line, re.IGNORECASE)
                if kv_match:
                    current_key = kv_match.group(1).lower()
                    result[current_key] = kv_match.group(2).strip()
                elif current_key and line:
                    # Append to existing key
                    result[current_key] = result.get(current_key, "") + " " + line
            
            if result:
                print(f"DEBUG - Created structured JSON from text: {list(result.keys())}")
                return json.dumps(result)
        except Exception as e:
            print(f"DEBUG - Failed to create structured JSON: {e}")
            pass
    
    # Last resort: wrap the cleaned text in a minimal JSON structure
    print("DEBUG - Using fallback JSON structure")
    return json.dumps({"feedback": cleaned_text, "grade": "70/100"})

def extract_grade(text):
    """
    Extract numerical grade from text.
    Looks for patterns like "65/100" or "grade: 75" and returns the numerical value.
    """
    import re
    
    print(f"DEBUG - extract_grade input: {text[:100]}...")
    
    if not text:
        print("DEBUG - Empty text in extract_grade")
        return None
    
    # Look for specific patterns like "65/100"
    grade_pattern = re.search(r'(\d+)\/100', text)
    if grade_pattern:
        grade = float(grade_pattern.group(1))
        print(f"DEBUG - Found grade pattern X/100: {grade}")
        return grade
    
    # Look for "grade: 75" or similar patterns
    grade_key_pattern = re.search(r'grade[\s:]+([\d.]+)', text, re.IGNORECASE)
    if grade_key_pattern:
        grade = float(grade_key_pattern.group(1))
        print(f"DEBUG - Found grade key pattern: {grade}")
        return grade
    
    # Look for any number between 0 and 100 that could be a grade
    number_pattern = re.search(r'\b([0-9]{1,2}|100)\b', text)
    if number_pattern:
        grade = float(number_pattern.group(1))
        print(f"DEBUG - Found number pattern: {grade}")
        return grade
    
    print("DEBUG - No grade pattern found")
    return None

def extract_section(text, *keywords):
    """
    Extract sections from the AI response based on keywords.
    """
    import re
    
    print(f"DEBUG - extract_section for keywords {keywords}")
    
    if not text:
        print("DEBUG - Empty text in extract_section")
        return "No information available."
    
    text_lower = text.lower()
    lines = text.split('\n')
    
    # Try to find sections with headings matching keywords
    for i, line in enumerate(lines):
        line_lower = line.lower()
        for keyword in keywords:
            if keyword.lower() in line_lower and i < len(lines) - 1:
                # Extract text until the next section or end
                section_text = []
                j = i + 1
                while j < len(lines) and not any(k.lower() in lines[j].lower() for k in 
                                               ['feedback:', 'grade:', 'summary:', 'glow:', 'grow:', 'think:', 'rubric:']):
                    if lines[j].strip():
                        section_text.append(lines[j])
                    j += 1
                if section_text:
                    result = " ".join(section_text).strip()
                    print(f"DEBUG - Found section for {keyword}: {result[:50]}...")
                    return result
    
    # Fallback: Look for sentences containing keywords
    for keyword in keywords:
        pattern = re.compile(r'[^.!?]*\b' + re.escape(keyword.lower()) + r'\b[^.!?]*[.!?]', re.IGNORECASE)
        matches = pattern.findall(text_lower)
        if matches:
            result = " ".join(matches).strip().capitalize()
            print(f"DEBUG - Found sentences with {keyword}: {result[:50]}...")
            return result
    
    print(f"DEBUG - No section found for keywords {keywords}")
    return "Information not explicitly provided in the feedback."

def evaluate_with_rubric(question, answer, criteria, school_level):
    """Generate AI evaluation using the provided criteria"""
    print(f"DEBUG - evaluate_with_rubric called for {school_level} level")
    
    prompt = f"""
    Evaluate this {school_level} school submission against CBSE criteria:
    
    QUESTION: {question}
    ANSWER: {answer}
    
    CRITERIA:
    {json.dumps(criteria, indent=2)}
    
    Provide:
    1. Detailed feedback in paragraph form
    2. Final grade out of 100
    Format: 'FEEDBACK: [your feedback]\nSCORE: [score]/100'
    """
    
    try:
        print("DEBUG - Sending prompt to model")
        response = client.chat_completion(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2000,
            temperature=0.7
        )
        response_text = response.choices[0].message.content
        print(f"DEBUG - Received response: {response_text[:100]}...")
        return response_text
    except Exception as e:
        print(f"DEBUG - AI evaluation error: {str(e)}")
        raise RuntimeError(f"AI evaluation failed: {str(e)}")

def parse_ai_score(ai_response):
    """Extract score from AI response text"""
    import re
    
    print(f"DEBUG - parse_ai_score input: {ai_response[:100]}...")
    
    match = re.search(r'SCORE:\s*(\d+\.?\d*)/100', ai_response)
    if match:
        score = float(match.group(1))
        print(f"DEBUG - Extracted score: {score}")
        return score
    
    print("DEBUG - No score found in AI response")
    return 0.0



@views.route('/check-grading-status/<job_id>', methods=['GET'])
@login_required
def check_grading_status(job_id):
    """
    Route to check the status of a background grading job.
    Returns JSON with current progress, status message, and results.
    """
    print(f"DEBUG - check_grading_status called for job_id: {job_id}")
    
    try:
        # Handle NaN or empty job IDs by returning the most recent job for the user
        if job_id == 'NaN' or not job_id or job_id.lower() == 'undefined':
            print(f"DEBUG - Invalid job_id: {job_id}, looking for recent jobs")
            
            # Find the most recent jobs
            recent_jobs = GradingJob.query.join(Assignment).join(Class).filter(
                Class.owner_id == current_user.id
            ).order_by(GradingJob.created_at.desc()).limit(5).all()
            
            if not recent_jobs:
                print("DEBUG - No recent jobs found for this user")
                return jsonify({
                    'status': 'Waiting for job to start...',
                    'progress': 0,
                    'complete': False
                })
            
            # Use the most recent active job, or the most recent job if none are active
            active_job = next((job for job in recent_jobs if job.status == 'processing'), None)
            job = active_job if active_job else recent_jobs[0]
            
            print(f"DEBUG - Found recent job: {job.id} with status: {job.status}")
        else:
            # Try a few different strategies to find the job
            
            # 1. Try exact ID match first
            job = GradingJob.query.get(job_id)
            
            # 2. Try prefix match (if the job ID is a UUID and we're getting a prefix)
            if not job:
                print(f"DEBUG - Job not found directly with ID: {job_id}, trying partial match")
                job = GradingJob.query.filter(GradingJob.id.like(f"{job_id}%")).first()
            
            # 3. Try suffix match (if we're getting the end part of the ID)
            if not job:
                print(f"DEBUG - No job found with ID prefix: {job_id}, trying suffix match")
                job = GradingJob.query.filter(GradingJob.id.like(f"%{job_id}")).first()
                
            # 4. Try contains match (if the ID is somewhere in the middle)
            if not job:
                print(f"DEBUG - No job found with ID suffix: {job_id}, trying contains match")
                job = GradingJob.query.filter(GradingJob.id.like(f"%{job_id}%")).first()
                
            # 5. If still not found, try to find the job by looking at recent jobs
            if not job:
                print(f"DEBUG - No job found containing ID: {job_id}, looking for recent jobs")
                # Find the most recent processing job for the current user
                recent_jobs = GradingJob.query.join(Assignment).join(Class).filter(
                    Class.owner_id == current_user.id
                ).order_by(GradingJob.created_at.desc()).limit(1).all()
                
                if recent_jobs:
                    job = recent_jobs[0]
                    print(f"DEBUG - Found recent job as fallback: {job.id}")
                else:
                    print(f"DEBUG - No job found with ID or recent jobs: {job_id}")
                    return jsonify({
                        'status': 'Initializing grading process...',
                        'progress': 5,
                        'complete': False
                    })
        
        print(f"DEBUG - Using job ID: {job.id} with status: {job.status}")
        
        # Check if the assignment exists
        assignment = Assignment.query.get(job.assignment_id)
        if not assignment:
            print(f"DEBUG - Assignment {job.assignment_id} not found")
            return jsonify({
                'status': 'Processing submissions...',
                'progress': 10,
                'complete': False,
                'job_id': job.id  # Return job ID so frontend knows which one we're talking about
            })
        
        # Check authorization
        # Modified to handle the case where current_user might not be related to the class
        is_authorized = False
        
        # Check if user is the owner of the class
        if hasattr(assignment, 'class_ref') and assignment.class_ref and hasattr(assignment.class_ref, 'owner_id'):
            is_authorized = (assignment.class_ref.owner_id == current_user.id)
        
        # Alternative check if user has classes relationship
        if not is_authorized and hasattr(current_user, 'classes') and assignment.class_ref:
            is_authorized = assignment.class_ref in current_user.classes
        
        if not is_authorized:
            print(f"DEBUG - Unauthorized access to job_id: {job.id}")
            return jsonify({
                'status': 'Processing submissions...',
                'progress': 10,
                'complete': False,
                'job_id': job.id
            })

        # Parse results if job is completed
        results = []
        if job.status == 'completed' and job.results:
            try:
                print(f"DEBUG - Parsing job results for job ID: {job.id}")
                results_data = json.loads(job.results)
                results = results_data.get('results', [])
                print(f"DEBUG - Found {len(results)} result items")
            except json.JSONDecodeError as e:
                print(f"DEBUG - Error parsing job results: {str(e)}")
                results = []

        # Calculate progress percentage
        progress = 0
        if hasattr(job, 'total_submissions') and job.total_submissions > 0:
            progress = round((job.processed_submissions / job.total_submissions) * 100, 1)
        elif job.processed_submissions > 0:
            # If we don't have total_submissions but have processed some, show indeterminate progress
            progress = 50  # Use 50% to indicate in-progress state
        
        # Get total submissions for display
        total_submissions = getattr(job, 'total_submissions', 0) 
        print(f"DEBUG - Progress: {progress}% ({job.processed_submissions}/{total_submissions if total_submissions > 0 else '?'})")
        
        # Create status message based on job status
        status_message = f"Processing submissions... ({job.processed_submissions}/{total_submissions if total_submissions > 0 else '?'})"
        if job.status == 'completed':
            status_message = f"Completed grading {job.processed_submissions} submissions"
        elif job.status == 'failed':
            status_message = "There was a problem processing some submissions"
        print(f"DEBUG - Status message: {status_message}")

        # Return comprehensive job status
        return jsonify({
            'id': job.id,
            'job_id': job.id,  # Including both formats for compatibility
            'status': status_message,
            'progress': progress,
            'complete': job.status in ['completed', 'failed'],
            'results': results,
            'timestamp': job.updated_at.isoformat() if hasattr(job, 'updated_at') else None,
            'assignment_id': job.assignment_id,
            'processed': job.processed_submissions,
            'total': total_submissions
        })

    except Exception as e:
        print(f"DEBUG - Error checking job status: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'status': 'Processing submissions...',
            'progress': 10,
            'complete': False
        })


@views.route('/grade-all-submissions/<int:assignment_id>', methods=['GET', 'POST'])
@login_required
def grade_all_submissions(assignment_id):
    """
    View for grading all submissions for a particular assignment using AI.
    Returns job ID for tracking progress.
    """
    assignment = Assignment.query.get_or_404(assignment_id)
    rubric = assignment.rubric

    if not rubric:
        flash('No rubric assigned to this assignment!', 'error')
        return redirect(url_for('views.view_class', class_id=assignment.class_id))

    submissions = Submission.query.filter_by(assignment_id=assignment_id).all()

    if not submissions:
        flash('No submissions found for this assignment!', 'warning')
        return redirect(url_for('views.view_class', class_id=assignment.class_id))

    if request.method == 'POST':
        try:
            # Get JSON data with proper error handling
            data = None
            try:
                data = request.get_json(silent=True)
            except Exception:
                data = {}
            
            # Ensure data is always a dictionary
            if data is None:
                data = {}
            
            # Use the skip_graded flag from the request data (default is True)
            skip_graded = data.get('skip_graded', True)

            to_grade = [s for s in submissions if (s.grade is None or not s.ai_feedback)] if skip_graded else submissions

            if not to_grade:
                return jsonify({
                    'status': 'complete',
                    'message': 'All submissions have already been graded.',
                    'total_submissions': 0
                })

            # Create a new grading job with the updated constructor parameters
            import uuid
            job_id = str(uuid.uuid4())
            job = GradingJob(
                assignment_id=assignment_id,
                job_id=job_id,  # Explicitly set a valid UUID
                processed_submissions=0,
                status='processing',
                total_submissions=len(to_grade)
            )

            db.session.add(job)
            db.session.commit()

            # Get current app for use in background thread
            from flask import current_app
            app = current_app._get_current_object()  # Get actual app object, not proxy

            # Instead of passing the rubric object, pass its ID
            rubric_id = rubric.id
            # Instead of passing submission objects, pass their IDs
            submission_ids = [s.id for s in to_grade]

            # Start background job in a separate thread
            thread = Thread(
                target=process_grading_job,
                args=(app, job.id, submission_ids, rubric_id, skip_graded)
            )
            thread.daemon = True
            thread.start()

            return jsonify({
                'job_id': job.id,
                'status': 'processing',
                'message': f'Started grading {job.total_submissions} submissions',
                'total_submissions': job.total_submissions
            })

        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({'error': str(e)}), 500

    # GET request handling: render grading page
    total_submissions = len(submissions)
    graded_submissions = len([s for s in submissions if s.grade is not None])
    ungraded_submissions = total_submissions - graded_submissions

    return render_template('grade_all_submissions.html',
                           assignment=assignment,
                           rubric=rubric,
                           total_submissions=total_submissions,
                           graded_submissions=graded_submissions,
                           ungraded_submissions=ungraded_submissions)


def process_grading_job(app, job_id, submission_ids, rubric_id, skip_graded=True):
    """
    Background function to process a grading job.
    Updates job status in the database as progress is made.
    """
    import json
    from .models import db, Submission, Rubric, GradingJob
    
    # Create an application context
    with app.app_context():
        job = GradingJob.query.get(job_id)
        if not job:
            return

        # Get the rubric from the database inside this context
        rubric = Rubric.query.get(rubric_id)
        if not rubric:
            job.status = 'failed'
            job.error_message = f"Rubric with ID {rubric_id} not found"
            db.session.commit()
            return

        results = []
        errors = []
        processed_count = 0
        
        try:
            rubric_criteria = rubric.get_criteria()

            for submission_id in submission_ids:
                try:
                    # Fetch submission from database inside this context
                    submission = Submission.query.get(submission_id)
                    if not submission:
                        errors.append({
                            'submission_id': submission_id,
                            'error': 'Submission not found'
                        })
                        processed_count += 1
                        job.processed_submissions = processed_count
                        db.session.commit()
                        continue

                    if skip_graded and submission.grade is not None and submission.ai_feedback:
                        results.append({
                            'submission_id': submission.id,
                            'student_name': submission.student.name if hasattr(submission, 'student') else 'Unknown',
                            'status': 'skipped',
                            'skipped': True,
                            'message': 'Already graded'
                        })
                        processed_count += 1
                        job.processed_submissions = processed_count
                        db.session.commit()
                        continue

                    # Safely get assignment question
                    question = getattr(submission.assignment_ref, 'question', "Question not available")
                    
                    # Safely get student answer
                    student_answer = getattr(submission, 'student_answer', "Answer not available")

                    prompt = f"""
                    You are an AI teaching assistant. Grade this student answer based on the provided rubric:
                    
                    Question: {question}
                    Student Answer: {student_answer}
                    
                    Rubric Criteria for {rubric.level} Level:
                    {json.dumps(rubric_criteria, indent=2)}
                    
                    Provide detailed feedback and a numerical grade between 0-100.
                    Format your response as a JSON object with the following keys:
                    - feedback: [detailed feedback]
                    - grade: [numerical grade as a string in format "X/100"]
                    - summary: [brief summary of the feedback]
                    - glow: [what the student did well]
                    - grow: [areas for improvement]
                    - think_about_it: [questions to ponder for improvement]
                    - rubric: [detailed rubric breakdown with scores and explanations]
                    
                    IMPORTANT GRADING INSTRUCTIONS:
                    1. If the student's answer is completely unrelated to the question, assign 0 marks and provide appropriate feedback.
                    2. If the content appears to be AI-generated, deduct marks appropriately and mention this concern in your feedback.
                    3. Return ONLY the JSON object with no markdown formatting, no backticks, and no code blocks.
                    
                    Your entire response must be a valid JSON object that can be directly parsed.
                    """

                    try:
                        response = model.generate_content(prompt)
                    except Exception as e:
                        raise RuntimeError(f"AI generation failed: {str(e)}")
                    
                    processed_text = clean_ai_response(response.text)

                    try:
                        feedback_data = json.loads(processed_text)
                        
                        # Ensure grade is properly formatted
                        if isinstance(feedback_data.get('grade'), str):
                            if '/' not in feedback_data['grade']:
                                feedback_data['grade'] = f"{feedback_data['grade']}/100"
                        elif isinstance(feedback_data.get('grade'), (int, float)):
                            feedback_data['grade'] = f"{feedback_data['grade']}/100"

                        # Ensure all expected keys are present
                        required_keys = ['feedback', 'grade', 'summary', 'glow', 'grow', 'think_about_it', 'rubric']
                        for key in required_keys:
                            if key not in feedback_data:
                                feedback_data[key] = {"rubric": {"Overall": "Assessment included in general feedback."}}[key] if key == 'rubric' else "Not provided in AI response."
                    
                    except json.JSONDecodeError:
                        feedback_data = {
                            'feedback': response.text,
                            'grade': extract_grade(response.text) or "70/100",
                            'summary': "AI provided feedback but not in the expected format.",
                            'glow': extract_section(response.text, "glow", "positive points", "strengths"),
                            'grow': extract_section(response.text, "grow", "improve", "weaknesses"),
                            'think_about_it': extract_section(response.text, "think", "consider", "reflect"),
                            'rubric': {"Overall": "See feedback for assessment details."}
                        }
                    
                    submission.ai_feedback = json.dumps(feedback_data)
                    
                    # Extract numerical grade
                    grade_value = 0
                    try:
                        if isinstance(feedback_data['grade'], str) and '/' in feedback_data['grade']:
                            grade_value = float(feedback_data['grade'].split('/')[0])
                        elif isinstance(feedback_data['grade'], (int, float)):
                            grade_value = float(feedback_data['grade'])
                    except (KeyError, ValueError, TypeError):
                        extracted = extract_grade(response.text)
                        grade_value = extracted if extracted is not None else 70

                    submission.grade = grade_value
                    
                    results.append({
                        'submission_id': submission.id,
                        'student_name': submission.student.name if hasattr(submission, 'student') else 'Unknown',
                        'status': 'success',
                        'grade': feedback_data['grade'],
                        'summary': feedback_data['summary']
                    })

                except Exception as e:
                    errors.append({
                        'submission_id': submission_id,
                        'error': str(e)
                    })
                    
                    # Get the submission again to ensure it's attached to this session
                    submission = Submission.query.get(submission_id)
                    if submission:
                        fallback_data = {
                            'feedback': "The AI grading system encountered an error. Please try again or grade manually.",
                            'grade': "70/100",
                            'summary': "Automatic grading encountered an error.",
                            'glow': "Unable to evaluate strengths due to system error.",
                            'grow': "Unable to evaluate areas for improvement due to system error.",
                            'think_about_it': "How might the system be improved to better evaluate this response?",
                            'rubric': {"Overall": "System error prevented detailed evaluation."}
                        }
                        
                        submission.ai_feedback = json.dumps(fallback_data)
                        submission.grade = 70
                        results.append({
                            'submission_id': submission.id,
                            'status': 'error',
                            'message': str(e)
                        })
                    
                processed_count += 1
                job.processed_submissions = processed_count
                db.session.commit()

            job.status = 'completed'
            job.results = json.dumps({
                'status': 'success',
                'results': results,
                'errors': errors
            })
            db.session.commit()
        
        except Exception as e:
            job.status = 'failed'
            job.error_message = str(e)
            db.session.commit()

@views.route('/send-grade/<int:submission_id>', methods=['POST'])
@login_required
def send_grade(submission_id):
    """
    Redirects to Gmail with pre-filled email content to send the grade to a student
    """
    # Get the submission from the database
    submission = Submission.query.get_or_404(submission_id)
    assignment = Assignment.query.get_or_404(submission.assignment_id)
    
    # Check if student email exists
    if not submission.student_email:
        return jsonify({"error": "Student email not found"}), 400
    
    # Get the feedback and grade information
    ai_feedback = submission.ai_feedback
    
    # Parse the feedback if it's stored as JSON
    feedback_dict = {}
    try:
        if ai_feedback and isinstance(ai_feedback, str):
            feedback_dict = json.loads(ai_feedback)
        elif ai_feedback:
            feedback_dict = ai_feedback
    except json.JSONDecodeError:
        # If it's not valid JSON, use it as is
        feedback_dict = {"feedback": ai_feedback}
    
    # Get the grade from the database or use the one from the feedback
    grade = submission.grade
    if not grade and "grade" in feedback_dict:
        grade = feedback_dict.get("grade")
    
    # Format the grade properly
    grade_str = str(grade) if grade else "N/A"
    if grade and not isinstance(grade, str) and not str(grade).endswith("/100"):
        grade_str = f"{grade}/100"
    
    # Construct email content
    subject = f"Grade for {assignment.name}"
    
    # Build the email body with available feedback components
    email_body = f"Dear {submission.student_name},\n\n"
    email_body += f"Your grade for {assignment.name} is: {grade_str}\n\n"
    
    if "feedback" in feedback_dict:
        email_body += f"Feedback:\n{feedback_dict.get('feedback')}\n\n"
    
    if "summary" in feedback_dict:
        email_body += f"Summary:\n{feedback_dict.get('summary')}\n\n"
    
    if "glow" in feedback_dict:
        email_body += f"What Went Well (Glow):\n{feedback_dict.get('glow')}\n\n"
    
    if "grow" in feedback_dict:
        email_body += f"Areas for Improvement (Grow):\n{feedback_dict.get('grow')}\n\n"
    
    if "think_about_it" in feedback_dict:
        email_body += f"Things to Think About:\n{feedback_dict.get('think_about_it')}\n\n"
    
    # Add a note about rubric if it exists
    if "rubric" in feedback_dict:
        email_body += "A detailed rubric evaluation was also performed.\n\n"
    
    email_body += "If you have any questions about your grade, please feel free to contact me.\n\n"
    email_body += f"Best regards,\n{current_user.name}"
    
    # Encode email parameters for Gmail
    params = {
        "view": "cm",
        "to": submission.student_email,
        "su": subject,
        "body": email_body
    }
    
    gmail_url = "https://mail.google.com/mail/?" + urllib.parse.urlencode(params)
    
    # Return success status (the frontend will handle the redirection)
    return jsonify({"success": True, "redirect_url": gmail_url})


@views.route('/import-google-classroom', endpoint='import_google_classroom')
@login_required
def import_google_classroom():
    # Use the client secret JSON directly from environment variable
    client_secret_json = json.loads(os.getenv("CLIENT_SECRET_JSON"))
    
    # Create a flow from the client secret json dictionary instead of a file
    flow = google_auth_oauthlib.flow.Flow.from_client_config(
        client_secret_json, scopes=SCOPES)
    flow.redirect_uri = url_for('views.oauth2callback', _external=True)
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent')  
    session['state'] = state
    return redirect(authorization_url)


@views.route('/oauth2callback', endpoint='oauth2callback')
@login_required
def oauth2callback():
    try:
        # Get state from session
        state = session.get('state')
        if not state:
            flash('Authentication session expired. Please try again.', 'error')
            return redirect(url_for('views.dashboard'))
        
        # Use the client secret JSON directly from environment variable
        client_secret_json = json.loads(os.getenv("CLIENT_SECRET_JSON"))
        
        # Create flow from client config instead of file
        flow = google_auth_oauthlib.flow.Flow.from_client_config(
            client_secret_json, scopes=SCOPES, state=state)
        flow.redirect_uri = url_for('views.oauth2callback', _external=True)
        
        # Fetch token
        authorization_response = request.url
        flow.fetch_token(authorization_response=authorization_response)
        
        # Store credentials
        credentials = flow.credentials
        
        # Explicitly check for refresh token
        if not credentials.refresh_token:
            print("No refresh token received. This may happen if the user has already granted access previously.")
            print("Adding prompt='consent' to force new refresh token.")
            return redirect(url_for('views.import_google_classroom'))
        
        # Print debug info
        print(f"Received credentials:")
        print(f"- Token: {credentials.token[:10]}... (truncated)")
        print(f"- Refresh token: {credentials.refresh_token[:10]}... (truncated)")
        print(f"- Token URI present: {'Yes' if credentials.token_uri else 'No'}")
        print(f"- Client ID present: {'Yes' if credentials.client_id else 'No'}")
        print(f"- Client secret present: {'Yes' if credentials.client_secret else 'No'}")
        
        token_data = {
            'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': credentials.scopes
        }
        
        # Make sure we have all necessary fields for refresh
        missing_fields = [field for field, value in token_data.items() 
                         if field in ['refresh_token', 'token_uri', 'client_id', 'client_secret'] and not value]
        
        if missing_fields:
            missing_fields_str = ', '.join(missing_fields)
            flash(f'Error: Failed to get complete Google credentials. Missing: {missing_fields_str}. Please try again.', 'error')
            return redirect(url_for('views.dashboard'))
        
        # Store the tokens
        current_user.google_tokens = json.dumps(token_data)
        db.session.commit()
        
        return redirect(url_for('views.select_google_class'))
    except Exception as e:
        flash(f'Error during authentication: {str(e)}', 'error')
        import traceback
        traceback.print_exc()
        return redirect(url_for('views.dashboard'))


def get_google_credentials():
    """
    Helper function to get refreshed Google credentials
    """
    if not current_user.google_tokens:
        print("No Google tokens found for user")
        return None
    
    try:
        token_data = json.loads(current_user.google_tokens)
        
        # Check if we have all required fields for refreshing
        required_fields = ['refresh_token', 'token_uri', 'client_id', 'client_secret']
        missing_fields = [field for field in required_fields if field not in token_data or not token_data[field]]
        
        if missing_fields:
            print(f"Missing required fields for token refresh: {', '.join(missing_fields)}")
            print(f"Available token data keys: {list(token_data.keys())}")
            # Re-authentication needed
            return None
        
        credentials = google.oauth2.credentials.Credentials(
            token=token_data.get('token'),
            refresh_token=token_data.get('refresh_token'),
            token_uri=token_data.get('token_uri'),
            client_id=token_data.get('client_id'),
            client_secret=token_data.get('client_secret'),
            scopes=token_data.get('scopes')
        )
        
        # Force refresh if token is expired
        if not credentials.valid:
            print("Token expired, attempting to refresh")
            request = google.auth.transport.requests.Request()
            credentials.refresh(request)
            
            # Update stored token
            current_user.google_tokens = json.dumps({
                'token': credentials.token,
                'refresh_token': credentials.refresh_token,
                'token_uri': credentials.token_uri,
                'client_id': credentials.client_id,
                'client_secret': credentials.client_secret,
                'scopes': credentials.scopes
            })
            db.session.commit()
            print("Token refreshed successfully")
        
        return credentials
    except Exception as e:
        print(f"Error refreshing credentials: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

def get_google_credentials():
    """
    Helper function to get refreshed Google credentials
    """
    if not current_user.google_tokens:
        print("No Google tokens found for user")
        return None
    
    try:
        token_data = json.loads(current_user.google_tokens)
        
        # Check if we have all required fields for refreshing
        required_fields = ['refresh_token', 'token_uri', 'client_id', 'client_secret']
        missing_fields = [field for field in required_fields if field not in token_data or not token_data[field]]
        
        if missing_fields:
            print(f"Missing required fields for token refresh: {', '.join(missing_fields)}")
            print(f"Available token data keys: {list(token_data.keys())}")
            # Re-authentication needed
            return None
        
        credentials = google.oauth2.credentials.Credentials(
            token=token_data.get('token'),
            refresh_token=token_data.get('refresh_token'),
            token_uri=token_data.get('token_uri'),
            client_id=token_data.get('client_id'),
            client_secret=token_data.get('client_secret'),
            scopes=token_data.get('scopes')
        )
        
        # Force refresh if token is expired
        if not credentials.valid:
            print("Token expired, attempting to refresh")
            request = google.auth.transport.requests.Request()
            credentials.refresh(request)
            
            # Update stored token
            current_user.google_tokens = json.dumps({
                'token': credentials.token,
                'refresh_token': credentials.refresh_token,
                'token_uri': credentials.token_uri,
                'client_id': credentials.client_id,
                'client_secret': credentials.client_secret,
                'scopes': credentials.scopes
            })
            db.session.commit()
            print("Token refreshed successfully")
        
        return credentials
    except Exception as e:
        print(f"Error refreshing credentials: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

@views.route('/select-google-class', endpoint='select_google_class', methods=['GET', 'POST'])
@login_required
def select_google_class():
    if request.method == 'POST':
        selected_class_id = request.form.get('class_id')
        return redirect(url_for('views.select_rubric', class_id=selected_class_id))
    
    # Get Google Classroom service using helper function
    credentials = get_google_credentials()
    if not credentials:
        flash('Google authentication expired. Please reconnect your Google account.', 'error')
        return redirect(url_for('views.import_google_classroom'))
    
    try:
        service = googleapiclient.discovery.build('classroom', 'v1', credentials=credentials)
        results = service.courses().list().execute()
        classes = results.get('courses', [])
        
        return render_template('select_google_class.html', classes=classes)
    except Exception as e:
        flash(f'Error accessing Google Classroom: {str(e)}', 'error')
        return redirect(url_for('views.dashboard'))

@views.route('/select-rubric/<class_id>', endpoint='select_rubric', methods=['GET', 'POST'])
@login_required
def select_rubric(class_id):
    if request.method == 'POST':
        rubric_id = request.form.get('rubric_id')
        # Create GoogleClass entry
        new_class = GoogleClass(
            google_classroom_id=class_id,
            rubric_id=rubric_id,
            name=request.form.get('class_name'),
            level=request.form.get('class_level'),
            owner_id=current_user.id,
            type='google'  # Explicitly set the type value
        )
        db.session.add(new_class)
        db.session.commit()
        
        # After creating the class, immediately import assignments
        import_assignments_from_google(new_class.id)
        
        return redirect(url_for('views.view_class', class_id=new_class.id))
    
    # Get Google Classroom service using helper function
    credentials = get_google_credentials()
    if not credentials:
        flash('Google authentication expired. Please reconnect your Google account.', 'error')
        return redirect(url_for('views.import_google_classroom'))
    
    try:
        service = googleapiclient.discovery.build('classroom', 'v1', credentials=credentials)
        gc_class = service.courses().get(id=class_id).execute()
        
        # Get both user-created rubrics and system-created default rubrics
        all_rubrics = Rubric.query.filter(
            (Rubric.creator_id == current_user.id) | (Rubric.creator_id == None)
        ).all()
        
        return render_template('select_rubric.html',
            class_name=gc_class['name'],
            rubrics=all_rubrics)
    except Exception as e:
        flash(f'Error accessing Google Classroom: {str(e)}', 'error')
        return redirect(url_for('views.dashboard'))

@views.route('/refresh-google-assignments/<int:class_id>', endpoint='refresh_google_assignments')
@login_required
def refresh_google_assignments(class_id):
    """
    Route to manually refresh assignments from Google Classroom
    """
    result = import_assignments_from_google(class_id)
    
    # Check if we need to redirect to authentication
    if session.pop('needs_google_auth', False):
        if request.headers.get('Accept') == 'application/json':
            return jsonify({
                'success': False, 
                'message': 'Authentication expired', 
                'redirect': url_for('views.import_google_classroom')
            }), 401
        else:
            return redirect(url_for('views.import_google_classroom'))
    
    # Return JSON response if it's an AJAX request
    if request.headers.get('Accept') == 'application/json':
        if result:
            return jsonify({'success': True, 'message': 'Assignments refreshed successfully'})
        else:
            return jsonify({'success': False, 'message': 'Failed to refresh assignments'}), 500
    
    if result:
        flash('Google Classroom assignments refreshed successfully', 'success')
    return redirect(url_for('views.view_class', class_id=class_id))

def import_assignments_from_google(class_id):
    """
    Helper function to import assignments from Google Classroom
    Returns True if successful, False otherwise
    """
    # Get the class
    google_class = GoogleClass.query.get(class_id)
    if not google_class:
        print(f"Class with ID {class_id} not found")
        return False
    
    if google_class.owner_id != current_user.id:
        print(f"User {current_user.id} does not have permission for class {class_id}")
        return False
    
    # Get Google Classroom service using helper function
    credentials = get_google_credentials()
    if not credentials:
        print("Failed to get Google credentials - redirecting user to authenticate")
        # Instead of just returning False, we'll store a flag in the session
        # to redirect the user to the authentication page
        session['needs_google_auth'] = True
        flash('Google authentication expired. Please reconnect your Google account.', 'error')
        return False
    
    # Get coursework (assignments)
    try:
        service = googleapiclient.discovery.build('classroom', 'v1', credentials=credentials)
        
        # List all coursework in the course
        print(f"Fetching coursework for Google Classroom ID: {google_class.google_classroom_id}")
        coursework_results = service.courses().courseWork().list(
            courseId=google_class.google_classroom_id).execute()
        coursework_items = coursework_results.get('courseWork', [])
        print(f"Found {len(coursework_items)} coursework items")
        
        # Process each coursework item
        for item in coursework_items:
            # Check if assignment already exists
            existing_assignment = Assignment.query.filter_by(
                name=item['title'], 
                class_id=google_class.id
            ).first()
            
            if not existing_assignment:
                # Create new assignment
                print(f"Creating new assignment: {item['title']}")
                new_assignment = Assignment(
                    name=item['title'],
                    question=item.get('description', ''),
                    class_id=google_class.id,
                    rubric_id=google_class.rubric_id
                )
                db.session.add(new_assignment)
                db.session.flush()  # Get the ID without committing
                
                # Import submissions for this assignment
                import_submissions_for_assignment(service, google_class.google_classroom_id, 
                                               item['id'], new_assignment.id)
            else:
                # Update existing assignment
                print(f"Updating existing assignment: {item['title']}")
                existing_assignment.question = item.get('description', '')
                
                # Refresh submissions for existing assignment
                import_submissions_for_assignment(service, google_class.google_classroom_id, 
                                               item['id'], existing_assignment.id)
        
        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        flash(f'Error importing assignments: {str(e)}', 'error')
        print(f"Error in import_assignments_from_google: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def list_student_submissions(service, course_id, coursework_id):
    """Retrieve all student submissions for a coursework."""
    print(f"Fetching student submissions for coursework ID: {coursework_id}")
    submissions_results = service.courses().courseWork().studentSubmissions().list(
        courseId=course_id, 
        courseWorkId=coursework_id
    ).execute()
    submissions = submissions_results.get('studentSubmissions', [])
    print(f"Found {len(submissions)} student submissions")
    return submissions

def list_students(service, course_id):
    """Retrieve all students in a class."""
    print(f"Fetching students for course ID: {course_id}")
    students_result = service.courses().students().list(courseId=course_id).execute()
    students = students_result.get('students', [])
    print(f"Found {len(students)} students")
    return students

def build_student_profile_map(service, students):
    """Create a mapping of user IDs to student profiles."""
    print("Building student profile map")
    student_profile_map = {}
    for s in students:
        if 'userId' in s and 'profile' in s:
            student_profile_map[s['userId']] = s['profile']
    print(f"Built profile map for {len(student_profile_map)} students")
    return student_profile_map

def fetch_student_profile(service, student_id):
    """Fetch student profile information."""
    print(f"Fetching profile for student ID: {student_id}")
    try:
        student_info = service.userProfiles().get(userId=student_id).execute()
        return {
            'name': {'fullName': student_info.get('name', {}).get('fullName', 'Unknown Student')},
            'emailAddress': student_info.get('emailAddress', '')  # Use empty string as default
        }
    except Exception as e:
        print(f"Error fetching student profile: {e}")
        # Return minimum profile information to avoid skipping the student
        return {
            'name': {'fullName': 'Unknown Student'},
            'emailAddress': ''
        }

def extract_text_from_vision_api(file_path, mime_type):
    """Extract text from files using Google Vision API."""
    print(f"Extracting text from file: {file_path} with mime type: {mime_type}")
    try:
        from google.cloud import vision
        vision_client = vision.ImageAnnotatorClient()
        
        with open(file_path, 'rb') as file:
            content = file.read()
        
        image = vision.Image(content=content)
        
        if mime_type.startswith('image/'):
            print("Processing as image")
            response = vision_client.text_detection(image=image)
            if response.text_annotations:
                extracted_text = response.text_annotations[0].description
                print(f"Extracted {len(extracted_text)} characters from image")
                return extracted_text
            else:
                print("No text detected in image")
                return ""
        else:
            # Process all other types as documents
            print(f"Processing {mime_type} as document")
            response = vision_client.document_text_detection(image=image)
            extracted_text = response.full_text_annotation.text
            print(f"Extracted {len(extracted_text)} characters from document")
            return extracted_text
    except Exception as e:
        print(f"Error in Vision API extraction: {e}")
        import traceback
        traceback.print_exc()
        return ""

def process_drive_file(service, file_id, file_title):
    """Retrieve file content from Google Drive."""
    print(f"Processing Drive file: {file_title} (ID: {file_id})")
    try:
        import googleapiclient.discovery
        import os
        import tempfile
        
        drive_service = googleapiclient.discovery.build('drive', 'v3', credentials=service._http.credentials)
        
        # Get file metadata
        file_metadata = drive_service.files().get(fileId=file_id, fields="mimeType, name").execute()
        mime_type = file_metadata.get('mimeType', '')
        print(f"File mime type: {mime_type}")
        
        # Get file content
        file_content = drive_service.files().get_media(fileId=file_id).execute()
        
        # Save to temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file_title)[1]) as temp_file:
            temp_file.write(file_content)
            temp_file_path = temp_file.name
            print(f"Saved file to temporary location: {temp_file_path}")
        
        # Process based on mime type
        extracted_text = ""
        if mime_type.startswith('text/'):
            # For text files, just read the content
            with open(temp_file_path, 'r', errors='ignore') as f:
                extracted_text = f.read()
            print(f"Read {len(extracted_text)} characters from text file")
        elif mime_type == 'application/pdf':
            # For PDFs, try to use PyPDF2 first
            try:
                import PyPDF2
                pdf_text = []
                with open(temp_file_path, 'rb') as f:
                    pdf_reader = PyPDF2.PdfReader(f)
                    for page_num in range(len(pdf_reader.pages)):
                        page = pdf_reader.pages[page_num]
                        page_text = page.extract_text()
                        if page_text:
                            pdf_text.append(page_text)
                extracted_text = "\n".join(pdf_text)
                print(f"Extracted {len(extracted_text)} characters from PDF using PyPDF2")
                
                # If no text was extracted, fall back to Vision API
                if not extracted_text.strip():
                    print("No text extracted with PyPDF2, falling back to Vision API")
                    extracted_text = extract_text_from_vision_api(temp_file_path, mime_type)
            except Exception as pdf_err:
                print(f"PyPDF2 extraction failed: {pdf_err}, falling back to Vision API")
                extracted_text = extract_text_from_vision_api(temp_file_path, mime_type)
        elif mime_type == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
            # For DOCX files, try to use python-docx
            try:
                import docx
                doc = docx.Document(temp_file_path)
                extracted_text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
                print(f"Extracted {len(extracted_text)} characters from DOCX using python-docx")
                
                # If no text was extracted, fall back to Vision API
                if not extracted_text.strip():
                    print("No text extracted with python-docx, falling back to Vision API")
                    extracted_text = extract_text_from_vision_api(temp_file_path, mime_type)
            except Exception as docx_err:
                print(f"DOCX extraction failed: {docx_err}, falling back to Vision API")
                extracted_text = extract_text_from_vision_api(temp_file_path, mime_type)
        elif mime_type.startswith('image/'):
            # For images, use Vision API
            extracted_text = extract_text_from_vision_api(temp_file_path, mime_type)
        else:
            # For other types, try conversion or extraction
            print(f"Handling unknown mime type: {mime_type}")
            
            # Try to use textract for advanced file types
            try:
                import textract
                extracted_text = textract.process(temp_file_path).decode('utf-8', errors='ignore')
                print(f"Extracted {len(extracted_text)} characters using textract")
                
                # If no text was extracted, fall back to Vision API
                if not extracted_text.strip():
                    print("No text extracted with textract, falling back to Vision API")
                    extracted_text = extract_text_from_vision_api(temp_file_path, mime_type)
            except Exception as textract_err:
                print(f"Textract extraction failed: {textract_err}, falling back to Vision API")
                extracted_text = extract_text_from_vision_api(temp_file_path, mime_type)
        
        # Clean up temporary file
        os.unlink(temp_file_path)
        print(f"Cleaned up temporary file: {temp_file_path}")
        
        return extracted_text
    except Exception as e:
        print(f"Error processing drive file: {e}")
        import traceback
        traceback.print_exc()
        return ""

def process_submission(service, submission, student_profile_map, course_id):
    """Process an individual student submission."""
    import json
    
    student_id = submission.get('userId')
    print(f"Processing submission for student ID: {student_id}")
    
    profile = student_profile_map.get(student_id)
    if not profile:
        print(f"Profile not found in map for student ID: {student_id}, fetching directly")
        profile = fetch_student_profile(service, student_id)
    
    student_name = profile.get('name', {}).get('fullName', 'Unknown Student')
    student_email = profile.get('emailAddress', '')  # Empty string as default
    print(f"Student: {student_name}, Email: {student_email}")
    
    student_answer = ""
    extracted_texts = []
    file_links = []
    
    if 'assignmentSubmission' in submission:
        assign_submission = submission['assignmentSubmission']
        
        # Check for text submission
        if 'text' in assign_submission:
            student_answer = assign_submission['text']
            print(f"Text submission found: {len(student_answer)} characters")
        
        # Check for file attachments
        if 'attachments' in assign_submission:
            print(f"Found {len(assign_submission['attachments'])} attachments")
            
            for attachment in assign_submission['attachments']:
                if 'driveFile' in attachment:
                    drive_file = attachment['driveFile']
                    file_id = drive_file['id']
                    file_title = drive_file.get('title', drive_file.get('name', 'Untitled File'))
                    
                    print(f"Processing attachment: {file_title} (ID: {file_id})")
                    
                    # Add to file links
                    file_links.append({
                        'name': file_title,
                        'id': file_id,
                        'type': 'drive',
                        'link': f"https://drive.google.com/file/d/{file_id}/view"
                    })
                    
                    # Extract text from file
                    extracted_text = process_drive_file(service, file_id, file_title)
                    
                    if extracted_text:
                        print(f"Successfully extracted {len(extracted_text)} characters from {file_title}")
                        # Store extracted text with file information
                        extracted_texts.append({
                            'file_name': file_title,
                            'file_id': file_id,
                            'text': extracted_text
                        })
                    else:
                        print(f"No text extracted from {file_title}")
                        # Store empty text information to acknowledge the file
                        extracted_texts.append({
                            'file_name': file_title,
                            'file_id': file_id,
                            'text': f"[No text content could be extracted from this file.]"
                        })
    
    # Format the extracted text to be included in student_answer
    full_answer = student_answer
    for extracted in extracted_texts:
        # Add delimiter and file information
        if full_answer:
            full_answer += "\n\n"
        full_answer += f"--- Text extracted from {extracted['file_name']} ---\n{extracted['text']}"
    
    # If no text was extracted at all, add a note
    if not full_answer.strip():
        full_answer = "[No text content was found in this submission.]"
    
    # Debug output
    print(f"Final student answer length: {len(full_answer)}")
    print(f"File links: {len(file_links)}")
    
    submission_data_json = json.dumps({'files': file_links}) if file_links else None
    return student_name, student_email, full_answer, submission_data_json


def save_submission(student_name, student_email, student_answer, assignment_id, submission_data_json):
    """Save or update submission in the database."""
    print(f"Saving submission for student: {student_name}, email: {student_email}, assignment: {assignment_id}")
    print(f"Student answer length: {len(student_answer)}")
    print(f"Has submission data: {'Yes' if submission_data_json else 'No'}")
    
    try:
        # If email is empty, generate a unique identifier for the student
        if not student_email:
            import hashlib
            import time
            # Generate a unique email-like identifier based on student name and timestamp
            timestamp = int(time.time())
            hash_obj = hashlib.md5(f"{student_name}_{timestamp}".encode())
            student_email = f"student_{hash_obj.hexdigest()[:8]}@placeholder.edu"
            print(f"Generated placeholder email for student: {student_email}")
        
        existing_submission = Submission.query.filter_by(
            student_email=student_email, 
            assignment_id=assignment_id
        ).first()
        
        if existing_submission:
            print(f"Updating existing submission ID: {existing_submission.id}")
            existing_submission.student_answer = student_answer
            existing_submission.student_name = student_name
            
            # Check if submission_data column exists
            if hasattr(Submission, 'submission_data'):
                existing_submission.submission_data = submission_data_json
                print("Updated submission_data field")
            else:
                print("submission_data column not found in Submission model")
            
            db.session.commit()
            print("Submission updated successfully")
        else:
            print("Creating new submission")
            # Create new submission object
            new_submission = Submission(
                student_name=student_name,
                student_email=student_email,
                student_answer=student_answer,
                assignment_id=assignment_id,
                grade=0  # Default grade
            )
            
            # Add submission_data if the column exists
            if hasattr(Submission, 'submission_data'):
                new_submission.submission_data = submission_data_json
                print("Added submission_data field")
            else:
                print("submission_data column not found in Submission model")
            
            db.session.add(new_submission)
            db.session.commit()
            print(f"New submission created with ID: {new_submission.id}")
        
        return True
    except Exception as e:
        db.session.rollback()
        print(f"Error saving submission: {e}")
        import traceback
        traceback.print_exc()
        return False

def import_submissions_for_assignment(service, course_id, coursework_id, assignment_id):
    """Main function to import student submissions for an assignment."""
    print(f"Importing submissions for assignment ID: {assignment_id}")
    try:
        # Get student submissions
        student_submissions = list_student_submissions(service, course_id, coursework_id)
        print(f"Found {len(student_submissions)} submissions")
        
        # Get students in the class
        students = list_students(service, course_id)
        print(f"Found {len(students)} students in the class")
        
        # Build student profile map
        student_profile_map = build_student_profile_map(service, students)
        print(f"Built profile map with {len(student_profile_map)} students")
        
        # Process each submission
        for submission in student_submissions:
            student_name, student_email, student_answer, submission_data_json = process_submission(
                service, submission, student_profile_map, course_id
            )
            
            # Process all students regardless of email status
            print(f"Saving submission for {student_name} ({student_email or 'no email'})")
            save_submission(student_name, student_email, student_answer, assignment_id, submission_data_json)
        
        return True
    except Exception as e:
        print(f"Error importing submissions: {e}")
        import traceback
        traceback.print_exc()
        return False

@views.route('/get-google-classroom-students/<int:class_id>', endpoint='get_google_classroom_students')
@login_required
def get_google_classroom_students(class_id):
    """Get students enrolled in a Google Classroom class"""
    google_class = GoogleClass.query.get(class_id)
    
    # Verify permissions
    if not google_class or google_class.owner_id != current_user.id:
        return jsonify({'error': 'Class not found or permission denied'}), 403
    
    # Get Google Classroom service
    try:
        credentials = get_google_credentials()
        if not credentials:
            return jsonify({'error': 'Google authentication expired. Please reconnect your account.'}), 401
        
        service = googleapiclient.discovery.build('classroom', 'v1', credentials=credentials)
        
        # Get students
        students_result = service.courses().students().list(
            courseId=google_class.google_classroom_id).execute()
        students = students_result.get('students', [])
        
        # Format student data
        student_list = []
        for student in students:
            profile = student.get('profile', {})
            student_list.append({
                'id': student.get('userId'),
                'name': profile.get('name', {}).get('fullName', 'Unknown Student'),
                'email': profile.get('emailAddress', '')
            })
        
        return jsonify(student_list)
    
    except Exception as e:
        print(f"Error fetching Google Classroom students: {str(e)}")
        return jsonify({'error': str(e)}), 500

@views.route('/view-attachment/<submission_id>/<file_id>', endpoint='view_attachment')
@login_required
def view_attachment(submission_id, file_id):
    """View a Google Drive attachment"""
    submission = Submission.query.get(submission_id)
    
    # Verify permissions
    if not submission or not submission.assignment or not submission.assignment.class_id:
        return "Submission not found", 404
    
    class_id = submission.assignment.class_id
    google_class = GoogleClass.query.get(class_id)
    
    if not google_class or google_class.owner_id != current_user.id:
        return "Permission denied", 403
    
    try:
        # Check if submission has submission_data attribute
        if not hasattr(submission, 'submission_data') or not submission.submission_data:
            return "No file data available", 404
        
        submission_data = json.loads(submission.submission_data)
        file_found = False
        
        # Find the specific file
        for file in submission_data.get('files', []):
            if file.get('id') == file_id:
                file_found = True
                
                # Handle different file types
                if file.get('type') == 'link':
                    return redirect(file.get('url'))
                
                # For drive files, redirect to the Google Drive viewer
                if file.get('type') == 'drive':
                    # If we already have a link, use it
                    if 'link' in file:
                        return redirect(file['link'])
                    
                    # Otherwise, create a direct Drive link
                    return redirect(f"https://drive.google.com/file/d/{file_id}/view")
        
        if not file_found:
            return "File not found in submission data", 404
        
    except Exception as e:
        print(f"Error viewing attachment: {str(e)}")
        return f"Error viewing attachment: {str(e)}", 500
    
def check_submission_data_column():
    """
    Check if the submission_data column exists in the Submission model
    """
    try:
        # Check if the column exists
        columns = [column.name for column in Submission.__table__.columns]
        return 'submission_data' in columns
    except Exception:
        return False
    


@views.route('/update-student-email/<submission_id>', methods=['POST'])
def update_student_email(submission_id):
    try:
        data = request.get_json()
        email = data.get('email')
        
        # Update the submission with the new email
        submission = Submission.query.get(submission_id)
        submission.student_email = email
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Email updated successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 400
    
@views.route('/get-extracted-text/<int:submission_id>/<file_id>', endpoint='get_extracted_text')
@login_required
def get_extracted_text(submission_id, file_id):
    """Get the extracted text from a specific file attachment"""
    submission = Submission.query.get(submission_id)
    
    # Verify permissions
    if not submission or not submission.assignment or not submission.assignment.class_id:
        return jsonify({"error": "Submission not found"}), 404
    
    class_id = submission.assignment.class_id
    google_class = GoogleClass.query.get(class_id)
    
    if not google_class or google_class.owner_id != current_user.id:
        return jsonify({"error": "Permission denied"}), 403
    
    try:
        # Check if submission has submission_data attribute
        if not hasattr(submission, 'submission_data') or not submission.submission_data:
            return jsonify({"error": "No file data available"}), 404
        
        submission_data = json.loads(submission.submission_data)
        file_found = False
        
        # Find the specific file in the submission data
        for file in submission_data.get('files', []):
            if file.get('id') == file_id:
                file_found = True
                
                # Parse the student_answer to find text extracted from this file
                if submission.student_answer:
                    # Look for the marker that indicates the start of extracted text for this file
                    marker = f"--- Text extracted from {file.get('name')} ---"
                    if marker in submission.student_answer:
                        # Get the text after the marker
                        parts = submission.student_answer.split(marker)
                        for i, part in enumerate(parts):
                            if i > 0:  # Skip the first part (before any marker)
                                # Get text until the next marker or end of text
                                extracted_text = part.split("--- Text extracted from")[0] if "--- Text extracted from" in part else part
                                return jsonify({"text": extracted_text.strip()})
                
                # If we can't find extracted text for this specific file
                return jsonify({"error": "No extracted text found for this file"}), 404
        
        if not file_found:
            return jsonify({"error": "File not found in submission data"}), 404
        
    except Exception as e:
        print(f"Error getting extracted text: {str(e)}")
        return jsonify({"error": f"Error getting extracted text: {str(e)}"}), 500
    

