


# 🧭 Tourist_Assistant

**Tourist_Assistant** is an intelligent, API-driven virtual assistant built using **FastAPI**, designed to enhance the experience of tourists by providing smart location-based services, LLM-powered responses, and map visualizations.

---

## 🌟 Features

- 🔐 User Authentication with OAuth2 (JWT token-based)
- 📍 POI ("To Visit") management – create, read, update, delete
- 🧠 AI Question Answering using LLMs + Retrieval-Augmented Generation (RAG)
- 🗺️ Pydeck-powered Map Visualization
- 📦 Modular FastAPI design for scalable deployment

---

## 🚀 Tech Stack

- **FastAPI** – Web API framework
- **PostgreSQL / SQLAlchemy** – Database ORM
- **JWT & OAuth2** – Secure auth
- **LLM (OpenAI or custom)** – AI question handling
- **Qdrant / FAISS** – Vector store for RAG
- **Pydeck** – Interactive geospatial map rendering

---

## 📡 API Endpoints

### 🔐 Auth

| Method | Endpoint         | Description               |
|--------|------------------|---------------------------|
| POST   | `/auth/`         | Register a new user       |
| POST   | `/auth/token`    | Login and get JWT token   |

---

### 📍 ToVisit Endpoints

| Method | Endpoint                          | Description                |
|--------|-----------------------------------|----------------------------|
| GET    | `/pydeck`                         | Show map                   |
| POST   | `/ragquery`                       | Ask question (RAG model)   |
| GET    | `/tovisits/`                      | Get all saved places       |
| POST   | `/tovisits/`                      | Create new place to visit  |
| GET    | `/tovisits/{tovisit_id}`          | Get place by ID            |
| PUT    | `/tovisits/{tovisit_id}`          | Update place by ID         |
| DELETE | `/tovisits/{tovisit_id}`          | Delete place by ID         |

---

### 🧠 LLM Endpoint

| Method | Endpoint        | Description                  |
|--------|-----------------|------------------------------|
| POST   | `/query`        | Ask a question (LLM only)    |

---

## 📥 Setup & Installation

### 1. Clone the Repo
```bash
git clone https://github.com/yourusername/Tourist_Assistant.git
cd Tourist_Assistant
````

### 2. Create Virtual Environment

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Run the API

```bash
uvicorn main:app --reload
```

> Visit `http://127.0.0.1:8000/docs` for Swagger UI

---

## 🔐 Authentication

Use the `/auth/token` endpoint with username and password to get a **JWT token**. Use this token in the "Authorize" button in Swagger to access secured endpoints.

---

## 🧠 RAG & LLM Integration

* `POST /ragquery`: Uses a retrieval-augmented generation pipeline (e.g., Qdrant + OpenAI) to answer user queries about tourist places.
* `POST /query`: Direct LLM call for general questions.

---

## 🗺️ Map Visualization

* `GET /pydeck`: Returns a Pydeck-compatible JSON for rendering points on an interactive map.

---

## 📁 Folder Structure (Suggested)

```
Tourist_Assistant/
├── main.py
├── models/              # SQLAlchemy models
├── routers/             # FastAPI routers (auth, tovisit, llm)
├── services/            # RAG, LLM, utils
├── database/            # DB connection/session
├── schemas/             # Pydantic models
├── assets/              # Static files or embeddings
├── requirements.txt
└── README.md
```

---

## 🧑‍💻 Contributing

Contributions are welcome! Please fork the repo and submit a pull request.

---

## 📜 License

Copyright (c) 2025 [hany elshafey] @AIC Saudi Arabia

All rights reserved.

This software is proprietary and confidential. Unauthorized copying of this file, via any medium, is strictly prohibited.

This software may not be copied, modified, distributed, or used without express written permission from the copyright holder.

For licensing inquiries, please contact: hanyelshafey@gmail.com


---

## 📬 Contact

Developed by [Hany Elshafey](https://www.linkedin.com/in/hanyelshafey)
📧 [hanyelshafey@gmail.com](mailto:hanyelshafey@gmail.com)

---

## 🌍 Future Plans

* 📲 Mobile app integration
* 🌐 Multilingual support
* 📌 Location-aware chatbot interface
* 🏙️ Smart city tourism dashboard

```

---

Let me know if you'd like to:
- Add an environment variable template (`.env`)
- Include example cURL or Postman requests
- Generate this as a downloadable `README.md` file
```
