import os
from pathlib import Path
import frontmatter
import markdown

POSTS_DIR = Path("content/posts")


def _parse_post(filepath: Path) -> dict:
    post = frontmatter.load(filepath)
    slug = filepath.stem
    html_content = markdown.markdown(post.content, extensions=["fenced_code", "tables", "toc", "md_in_html"])
    return {
        "slug": slug,
        "title": post.get("title", slug.replace("-", " ").title()),
        "date": str(post.get("date", "")),
        "tags": post.get("tags", []),
        "summary": post.get("summary", ""),
        "content": html_content,
    }


def get_all_posts() -> list[dict]:
    if not POSTS_DIR.exists():
        return []
    posts = [_parse_post(f) for f in sorted(POSTS_DIR.glob("*.md"), reverse=True)]
    return posts


def get_recent_posts(limit: int = 3) -> list[dict]:
    return get_all_posts()[:limit]


def get_post_by_slug(slug: str) -> dict | None:
    filepath = POSTS_DIR / f"{slug}.md"
    if not filepath.exists():
        return None
    return _parse_post(filepath)
