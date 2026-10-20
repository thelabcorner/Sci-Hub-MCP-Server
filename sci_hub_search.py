import sys
import re
import os
import logging
import urllib3
import requests

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s", stream=sys.stderr, encoding="utf-8")

try:
    from altcha import solve_challenge_v1, PayloadV1
    _ALTCHA_AVAILABLE = True
except Exception:
    _ALTCHA_AVAILABLE = False

MIRRORS = [
    "sci-hub.ru",
    "sci-hub.st",
    "sci-hub.su",
    "sci-hub.box",
    "sci-hub.red",
    "sci-hub.al",
    "sci-hub.mk",
    "sci-hub.ee",
]


def _make_session():
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0"})
    return s


def _solve_altcha(session, base, page_html):
    if not _ALTCHA_AVAILABLE:
        return False
    m = re.search(r"/captcha/solution/(\d+)", page_html)
    if not m:
        return False
    sid = m.group(1)
    try:
        ch = session.get(f"https://{base}/captcha/challenge/{sid}", verify=False, timeout=20).json()
    except Exception as e:
        logging.warning("Sci-Hub challenge fetch error: %s", e)
        return False
    try:
        sol = solve_challenge_v1(ch["challenge"], salt=ch["salt"], algorithm=ch["algorithm"], max_number=ch["maxNumber"])
    except Exception as e:
        logging.warning("Sci-Hub altcha solve error: %s", e)
        return False
    try:
        payload = PayloadV1(ch["algorithm"], ch["challenge"], sol.number, ch["salt"], ch["signature"]).to_base64()
    except Exception as e:
        logging.warning("Sci-Hub payload build error: %s", e)
        return False
    try:
        resp = session.post(f"https://{base}/captcha/solution/{sid}", json={"captcha": payload}, verify=False, timeout=20)
        return bool(resp.json().get("success"))
    except Exception as e:
        logging.warning("Sci-Hub solution post error: %s", e)
        return False


def _fetch_page(session, base, path):
    url = f"https://{base}/{path.lstrip('/')}"
    try:
        return session.get(url, verify=False, timeout=20)
    except Exception as e:
        logging.warning("Sci-Hub request error (%s): %s", base, e)
        return None


def _is_captcha(html):
    return "проверка на робота" in html


def _extract_pdf_url(html, base):
    patterns = [
        r'<object[^>]*data="([^"]+\.pdf[^"]*)"',
        r'href="([^"]+\.pdf)"',
        r'(/storage/[^\s"\']+\.pdf)',
    ]
    for pat in patterns:
        m = re.search(pat, html, re.I)
        if m:
            url = m.group(1)
            if url.startswith("/"):
                url = f"https://{base}{url}"
            elif url.startswith("//"):
                url = f"https:{url}"
            return url
    return None


def _extract_meta(html, name):
    m = re.search(r'<meta[^>]+name=["\']' + re.escape(name) + r'["\'][^>]*content=["\']([^"\']*)["\']', html, re.I)
    if m:
        return m.group(1).strip()
    m = re.search(r'<meta[^>]+content=["\']([^"\']*)["\'][^>]*name=["\']' + re.escape(name) + r'["\']', html, re.I)
    if m:
        return m.group(1).strip()
    return ""


def _fetch_paper(identifier):
    for base in MIRRORS:
        resp = _fetch_page(requests.Session(), base, identifier)
        # need a single session across captcha solve + refetch; redo below
        break
    # Use one session for the chosen mirror
    for base in MIRRORS:
        session = _make_session()
        resp = _fetch_page(session, base, identifier)
        if resp is None or resp.status_code != 200:
            continue
        html = resp.text
        if _is_captcha(html):
            ok = _solve_altcha(session, base, html)
            if not ok:
                continue
            resp = _fetch_page(session, base, identifier)
            if resp is None or resp.status_code != 200:
                continue
            html = resp.text
            if _is_captcha(html):
                continue
        pdf_url = _extract_pdf_url(html, base)
        if not pdf_url:
            continue
        title = _extract_meta(html, "citation_title") or _extract_meta(html, "og:title")
        author = _extract_meta(html, "citation_author")
        year = _extract_meta(html, "citation_date") or _extract_meta(html, "citation_year") or _extract_meta(html, "citation_publication_date")
        year = re.search(r"\d{4}", year).group(0) if year and re.search(r"\d{4}", year) else year
        return {
            "doi": identifier if not identifier.startswith("http") else identifier,
            "pdf_url": pdf_url,
            "status": "success",
            "title": title,
            "author": author,
            "year": year,
            "_session": session,
        }
    return None


def search_paper_by_doi(doi):
    result = _fetch_paper(doi)
    if result is None:
        logging.warning("Sci-Hub paper not found for DOI: %s", doi)
        return {"doi": doi, "status": "not_found"}
    result.pop("_session", None)
    return result


def search_paper_by_title(title):
    # Resolve DOI via Crossref first
    try:
        url = f"https://api.crossref.org/works?query.title={requests.utils.quote(title)}&rows=1"
        response = requests.get(url, timeout=20)
        if response.status_code == 200:
            data = response.json()
            items = data.get("message", {}).get("items", [])
            if items:
                doi = items[0].get("DOI")
                if doi:
                    return search_paper_by_doi(doi)
    except Exception as e:
        logging.warning("CrossRef search error: %s", str(e))
    return {"title": title, "status": "not_found"}


def search_papers_by_keyword(keyword, num_results=10):
    papers = []
    try:
        url = f"https://api.crossref.org/works?query={requests.utils.quote(keyword)}&rows={num_results}"
        response = requests.get(url, timeout=20)
        if response.status_code == 200:
            data = response.json()
            for item in data.get("message", {}).get("items", []):
                doi = item.get("DOI")
                if doi:
                    result = search_paper_by_doi(doi)
                    if result.get("status") == "success":
                        papers.append(result)
    except Exception as e:
        logging.warning("Sci-Hub keyword search error: %s", str(e))
    return papers


def download_paper(pdf_url, output_path):
    try:
        session = _make_session()
        # If a captcha is required for the PDF host, it usually is not; direct GET.
        resp = session.get(pdf_url, verify=False, timeout=60, stream=True)
        if resp.status_code != 200:
            logging.warning("Sci-Hub download failed: HTTP %s", resp.status_code)
            return False
        with open(output_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        return True
    except Exception as e:
        logging.warning("Sci-Hub download error: %s", str(e))
        return False


if __name__ == "__main__":
    logging.info("Sci-Hub search module self-test")
    print(search_paper_by_doi("10.1038/nature09492"))
