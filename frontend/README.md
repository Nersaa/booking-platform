# Frontend

A small React + TypeScript showcase of the API: search on the map, a listing page with
prices and free dates, booking, payment and "My bookings".

```bash
npm install
npm run dev      # http://localhost:5173, uses the API of the running Docker Compose stack
npm run lint
npm run build
```

| Folder | What is inside |
|---|---|
| `src/api` | `client.ts`: fetch wrapper with JWT and token refresh; `types.ts`: response types |
| `src/pages` | Search, Listing, Login, My bookings |
| `src/components` | Map with price tags, listing card, booking box, header |
| `src/auth.tsx` | Who is logged in (React context) |

Libraries: React Router for pages, TanStack Query for requests, Leaflet for the map.
