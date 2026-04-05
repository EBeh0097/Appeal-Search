# Appeal-Search

CMS Appeals search — a [Streamlit](https://streamlit.io) app for searching Medicare and Medicaid appeal decisions.

## Running locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploying to Streamlit Community Cloud

1. Push this repository to GitHub (all files must be committed, including `app.py`, `requirements.txt`, and `.streamlit/config.toml`).
2. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with your GitHub account.
3. Click **New app**.
4. Select this repository (`EBeh0097/Appeal-Search`) and the branch you want to deploy.
5. Set the **Main file path** to `app.py`.
6. Expand **Advanced settings** and enter your desired **Custom subdomain** (e.g. `appeal-search`). Your app will then be available at `https://appeal-search.streamlit.app`.
7. Click **Deploy**.

> **Note:** Custom subdomains must be globally unique across all Streamlit Community Cloud apps. If your chosen subdomain is already taken, Streamlit will prompt you to choose a different one.

## Project structure

```
Appeal-Search/
├── app.py                  # Streamlit entry point
├── requirements.txt        # Python dependencies
└── .streamlit/
    └── config.toml         # App theme and server settings
```
