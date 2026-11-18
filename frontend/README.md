# Frontend

A small React + TypeScript showcase of the API: search with a map, a listing page with
a photo gallery, prices and free dates, booking, payment and "My bookings"; for hosts,
adding and editing places with photos, prices and closed dates.

```bash
npm install
npm run dev      # http://localhost:5173, uses the API of the running Docker Compose stack
npm run lint
npm run build
```

| Folder | What is inside |
|---|---|
| `src/api` | `client.ts`: fetch wrapper with JWT and token refresh; `types.ts`: response types |
| `src/pages` | Search, Listing, Login, My bookings, one booking with payment, Saved, Profile, Help, Hosting, Add a place, edit a place |
| `src/components` | Map with price tags, listing card, gallery, booking box, date picker, header |
| `src/components/host` | Listing form with a map to pick the point, photo uploads, prices, closed dates |
| `src/auth.tsx` | Who is logged in (React context) |

Libraries: React Router for pages, TanStack Query for requests, Leaflet for the map.
