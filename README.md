# Scrapper - Web Scraping Application

A FastAPI-based web application for scraping company and contact information with a modern, dark-themed Bootstrap UI.

## Features

- **Dark Theme**: Clean, minimal design with a dark color scheme
- **Responsive UI**: Works on desktop and mobile devices
- **Interactive Sidebar**: Collapsible sidebar for search history
- **Company Search**: Search for companies and view detailed information
- **Contact Management**: View and expand contact details for each company
- **Multi-page Application**: Dedicated pages for search, contacts, email, call, and settings

## Project Structure

```
scrapper/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── models.py
│   ├── routes.py
│   ├── database.py
│   └── services/
│       ├── __init__.py
│       └── scraper.py
├── static/
│   ├── css/
│   │   └── style.css
│   ├── js/
│   │   └── main.js
│   └── img/
│       └── logo.svg
└── templates/
    ├── base.html
    ├── index.html
    ├── search.html
    ├── contacts.html
    ├── email.html
    ├── call.html
    └── settings.html
```

## Setup and Installation

### Prerequisites

- Python 3.8 or higher
- pip (Python package manager)

### Installation Steps

1. Clone the repository:
   ```bash
   git clone https://github.com/your-username/scrapper.git
   cd scrapper
   ```

2. Create a conda environment:
   ```bash
   conda env create -f environment.yaml
   ```
3. Activate the environment:
   ```bash
   conda env create -f environment.yaml
   ```

4. Run the application:
   ```bash
   python -m app.main
   ```

5. Access the application in your browser:
   ```
   http://localhost:8000
   ```

## Usage

1. **Homepage**: Navigate through the main menu buttons to access different features
2. **Search**: Enter search queries like "top insurance companies in NY" to retrieve company data
3. **Contacts**: View and manage contact information
4. **Email**: Compose emails to contacts (mock functionality)
5. **Call**: Manage calls and view call history (mock functionality)
6. **Settings**: Configure application preferences

## Development

This application is built with:

- **FastAPI**: Modern, high-performance web framework
- **SQLAlchemy**: SQL toolkit and ORM
- **Jinja2**: Template engine
- **Bootstrap 5**: Frontend CSS framework
- **SQLite**: Lightweight database

## Notes

- The scraper.py service contains mock data for demonstration purposes. In a production environment, you would implement actual web scraping functionality
- The application features a complete UI but some functionality is simulated for demonstration purposes