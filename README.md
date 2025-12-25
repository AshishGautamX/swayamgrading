# AI-Powered Grading App

## Overview

In today’s fast-paced academic world, grading assignments manually can be time-consuming and inefficient. This Flask-based web application simplifies the grading process by leveraging AI and rubric-based evaluation, ensuring accurate and insightful feedback for students.

## Key Features

🔹 **Seamless Class Creation**: Teachers can create a class manually or import from Google Classroom effortlessly.
🔹 **Rubric-Based Grading**: Assignments are evaluated using predefined rubrics, or teachers can customize their own.
🔹 **AI-Generated Feedback**: The app automatically analyzes student performance and provides detailed feedback, highlighting strengths and areas for improvement.
🔹 **Google Cloud Integration**: Smoothly integrates with Google People, Gemini, and Classroom APIs, with Vision API coming soon!
🔹 **Student-Centric Insights**: Generates performance reports that help students understand their progress and areas for improvement.

## Tech Stack

* **Backend**: Flask (Python)
* **Frontend**: HTML, CSS, JavaScript
* **Database**: SQLite3 (default file-based database in Flask)
* **APIs**: Google People API, Gemini API, Google Classroom API (Vision API upcoming)
* **Hosting**: Render (for free hosting)

## Installation

### Prerequisites

Ensure you have the following installed:

* Python 3.x
* SQLite3 (already comes pre-installed with Python)
* Virtual Environment (venv)

### Steps to Run the App

1. Clone the repository:

   ```bash
   git clone <repo-url>
   cd grading-app
   ```
2. Create a virtual environment and activate it:

   ```bash
   python -m venv venv
   source venv/bin/activate  # For macOS/Linux
   venv\Scripts\activate     # For Windows
   ```
3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```
4. Set up the environment variables:

   ```bash
   export FLASK_APP=app.py
   export FLASK_ENV=development
   ```
5. Run the application:

   ```bash
   flask run
   ```
6. Open `http://127.0.0.1:5000/` in your browser.

## Contribution

Contributions are welcome! Feel free to submit issues or pull requests.

## License

This project is licensed under the MIT License.

## Contact

For any queries, reach out to ashishgautam835@gmail.com
