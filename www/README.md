# innomight.com

The Innomight Labs company website. React + [vite-react-ssg](https://github.com/Daydreamer-riri/vite-react-ssg):
every route is prerendered to static HTML at build time, then hydrated in the browser. Served by nginx
(`nginx.conf`) and deployed by `.forgejo/workflows/pipeline.yml`.

```
yarn dev      # http://localhost:5173, contact form posts to http://localhost:8000
yarn build    # type-check, prerender every page to dist/ and write dist/sitemap.xml
yarn preview  # serve dist/ locally
```

## Layout

```
src/
├── content/      # The facts: company details, products, services, navigation, process copy
├── components/   # Reusable UI, one folder per component: Name.tsx + style.module.css
├── pages/        # One folder per route: Page.tsx + style.module.css
├── hooks/        # useTheme, useDisclosure, useContactForm, useScrollToHash
├── services/     # Talking to the API (contact enquiries)
├── styles/       # tokens.css (themes) and global.css (reset and base typography)
└── routes.tsx    # Route table; every static path is prerendered
```

Styling is CSS Modules only, mobile first (`min-width` media queries at `40rem` and `64rem`).
Components read semantic tokens such as `--color-surface` and never hard-code theme colours.

## Common changes

- **Company details, certifications or frameworks**: edit `src/content/site.ts`. The footer disclosures
  and credentials strip appear once the fields are filled in.
- **Add a product**: add an entry to `src/content/products.ts`. Its `/software/<slug>` page, header menu
  entry, cards, footer link and sitemap entry all follow from that entry.
- **Product launch video**: set `video` on the product. It replaces the illustration on the home
  spotlight and the product page.
- **Add a theme**: add a `[data-theme='name']` block to `src/styles/tokens.css` and the name to `themes`
  in `src/hooks/useTheme.ts`.

The contact form posts to `POST /contact/enquiry` on the API (`api/src/contact/router.py`), which emails
the enquiry to `ENQUIRY_INBOX`. The API base URL comes from `.env.development` / `.env.production`.
