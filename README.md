# Integral Leadership Design

Static website built with Hugo for Integral Leadership Design.

**Site:** https://integralleadershipdesign.com

## Project Structure

```
hugo-site/
├── content/          # Markdown pages (40 leadership & coaching articles)
├── layouts/          # Custom HTML templates
│   ├── baseof.html   # Master layout
│   ├── index.html    # Homepage
│   ├── _default/
│   │   └── single.html
│   └── partials/     # Reusable components
├── static/           # Assets (CSS, JS, images)
└── hugo.toml         # Site configuration
```

## Features

- **Custom Layout** — No theme bloat; full control over design
- **Responsive Design** — Mobile-optimized CSS with breakpoints
- **Clean Content** — 40 extracted pages from WordPress (spam removed)
- **Fast Builds** — Hugo compiles in ~43ms
- **GitHub Pages** — Automated deployment via GitHub Actions

## Development

### Local Preview
```bash
hugo server -D
```
Opens at http://localhost:1313

### Build for Production
```bash
hugo --gc --minify
```
Output goes to `/public` directory.

## Deployment

**Automatic:** Push to main branch → GitHub Actions builds and deploys to Pages.

**Custom Domain:** Configure DNS at domain registrar pointing to GitHub Pages.

## Content

- Leadership coaching programs
- Change management consulting
- Women's leadership development
- Corporate development services
- Blog posts on leadership topics

## Technology

- **Static Generator:** Hugo v0.157+
- **Hosting:** GitHub Pages
- **DNS:** (Configure custom domain in GitHub settings)
- **CI/CD:** GitHub Actions

## License

Copyright © 2019-2026 Integral Leadership Design. All rights reserved.
