# Detection of Anomalies and Attacks in Databases Using Machine Learning: PharmaPulse — A Demonstration Web Application

Final thesis project — The aim of the work is to implement a system for detecting anomalies and potential attacks in databases using machine learning methods. To analyze security challenges in working with databases, the most common types of attacks with an emphasis on SQL injection, and existing approaches to detecting anomalies and malicious activities in information systems. To develop a prototype system for analyzing and classifying SQL queries using **supervised and unsupervised learning techniques**. To train and evaluate the machine learning model on **publicly available datasets containing legitimate and malicious SQL queries**. **To implement a demonstration web application that will enable the demonstration of the work of the developed model for detecting suspicious activities and potential attacks.** To assess the effectiveness of the system standard evaluation metrics are to be used.

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

### Datasets
```bash
Quetel, G., Pautet, L., Alata, E., Robert, T., & Gimenez, P.-F. (2025). Superviz25-SQL: SQL Injection Detection Dataset [Data set]. Zenodo. https://doi.org/10.5281/zenodo.17086037
```
```bash
(OPTIONAL GENERATED DATASET) ml/datasets/generate_login_dataset.py
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
mysql -u root -p pharmapulse < pharmapulse_base.sql
```

7. (OPTIONAL) Run the generated dataset:
```bash
python3 ml/datasets/generate_login_dataset.py
```

8. Run ml training:
```bash
python3 ml/train.py      
```

9. Run the application:
```bash
python3 app.py
```

The app will be available at `http://127.0.0.1:5000`

## Project Structure

```
pharmapulse_app/
├── ml/                     # Folder for ml training
│   ├── dataset/
│       ├── model/
│       ├── dataset_clean.csv
│       ├── dataset_login_generated.csv
│       └── generate_login_dataset.py
│   ├── __init__.py
│   ├── train.py            # ML training
│   └── plots/
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
