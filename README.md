# PharmaPulse — Anomaly and Attack Detection System in Databases

Final thesis project — Implementation of a system for anomaly and potential attack detection in databases using machine learning methods.

## About

PharmaPulse is a demo pharmacy web application used as an environment for researching database security attacks, with a focus on SQL injection. The system uses machine learning (Random Forest and Isolation Forest) to classify and detect malicious SQL queries in real time.

## Technologies

- **Backend:** Python, Flask
- **Database:** MySQL
- **Machine Learning:** scikit-learn (Random Forest, Isolation Forest)
- **Frontend:** HTML, CSS, JavaScript, Jinja2

## Installation

### Prerequisites
- Python 3.9+
- MySQL server

### Steps

1. Clone the repository:
```bash
git clone https://github.com/viserionnina/pharmapulse_app_for_detection_of_anomalies_attacks_in_databases_using_ml.git
cd pharmapulse_app_for_detection_of_anomalies_attacks_in_databases_using_ml
```

2. Create and activate a virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create a `.env` file:
```
MYSQL_HOST=localhost
MYSQL_USER=root
MYSQL_PASSWORD=your_password
MYSQL_DB=pharmapulse
SECRET_KEY=your-secret-key
```

5. Import the database:
```bash
mysql -u root -p pharmapulse < pharmapulse_base.sql
```

6. Run the application:
```bash
python3 app.py
```

The app will be available at `http://127.0.0.1:5000`

## Project Structure

```
pharmapulse_app/
├── ml_training             # Folder for ml training
├── dataset/
│   ├── Train.csv
│   ├── Val.csv
│   └── Test.csv
├── app.py                  # Main Flask application
├── pharmapulse_base.sql    # Database schema and seed data
├── requirements.txt        # Python dependencies
├── .env                    # Local environment variables (not in repo)
├── static/                 # CSS, JS, images
└── templates/              # HTML templates
```

## Author

Nicole Ivanković, 
University of Rijeka, Faculty of Engineering, Croatia
