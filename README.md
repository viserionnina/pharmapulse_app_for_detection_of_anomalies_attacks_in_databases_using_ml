# Detection of Anomalies and Attacks in Databases Using Machine Learning: PharmaPulse — A Demonstration Web Application

Final thesis project — The aim of the work is to implement a system for detecting anomalies and potential attacks in databases using machine learning methods. To analyze security challenges in working with databases, the most common types of attacks with an emphasis on SQL injection, and existing approaches to detecting anomalies and malicious activities in information systems. To develop a prototype system for analyzing and classifying SQL queries using **supervised and unsupervised learning techniques**. To train and evaluate the machine learning model on **publicly available datasets containing legitimate and malicious SQL queries**. **To implement a demonstration web application that will enable the demonstration of the work of the developed model for detecting suspicious activities and potential attacks.** To assess the effectiveness of the system standard evaluation metrics are to be used.

## About

PharmaPulse is a demo pharmacy web application used as an environment for researching database security attacks, with a focus on SQL injection. The system uses machine learning (Random Forest and Isolation Forest) to classify and detect malicious SQL queries in real time.

## Technologies

- **Backend:** Python 3.9, Flask
- **Database:** MySQL
- **Machine Learning:** scikit-learn (Random Forest, Isolation Forest)
- **Frontend:** HTML, CSS, JavaScript, Jinja2

## Installation

### Prerequisites
- Python 3.9+
- MySQL server (or Docker)

### Datasets
```bash
Quetel, G., Pautet, L., Alata, E., Robert, T., & Gimenez, P.-F. (2025). Superviz25-SQL: SQL Injection Detection Dataset [Data set]. Zenodo. https://doi.org/10.5281/zenodo.17086037
```

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
mysql -u root -p pharmapulse < db/pharmapulse_base.sql
```

6. Run ml training:
```bash
python3 ml/train.py      
```

7. Run the application:
```bash
python3 app.py
```

The app will be available at `http://127.0.0.1:5001`

## Docker

Alternatively, run the application using Docker (no local MySQL required):

```bash
cd docker
docker-compose up --build
```

The app will be available at `http://localhost:5001`. MySQL runs inside Docker and is automatically initialized with the database schema and seed data from `db/pharmapulse_base.sql`.

> **Note:** Create a `.env` file in the project root before running Docker (same as step 4 above).

## Project Structure

```
pharmapulse_app/
├── .github/workflows/
├── db/  
├── docker/  
├── ml/                         # Folder for ml training
│   ├── datasets/
│   │   ├── models/
│   │   │   ├── DS1/
│   │   │   ├── DS2/
│   │   │   ├── DS3/
│   │   │   ├── DS4/
│   │   │   ├── DS5/
│   │   │   └── DS6/
│   │   └── dataset_clean.csv   # Prepared dataset for ML training
│   ├── __init__.py
│   ├── train.py            # ML training
│   ├── detector.py         # ML detection
│   ├── if_features.py      # Isolation Forest SQL keyword features
│   └── plots/
│       ├── DS1/
│       ├── DS2/
│       ├── DS3/
│       ├── DS4/
│       ├── DS5/
│       └── DS6/
├── static/                 # CSS, JS, images
├── templates/              # HTML templates
├── app.py                  # Main Flask application
├── pharmapulse_base.sql    # Database schema and seed data
├── requirements.txt        # Python dependencies
├── .env                    # Local environment variables (not in repo)
└── LICENSE                 # MIT License
```

## Author

Nicole Ivanković, 
University of Rijeka, Faculty of Engineering, Croatia
