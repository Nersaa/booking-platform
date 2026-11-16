import { Route, Routes } from 'react-router-dom'

import Header from './components/Header'
import BookingsPage from './pages/BookingsPage'
import ListingPage from './pages/ListingPage'
import LoginPage from './pages/LoginPage'
import SearchPage from './pages/SearchPage'

export default function App() {
  return (
    <>
      <Header />
      <Routes>
        <Route path="/" element={<SearchPage />} />
        <Route path="/listings/:id" element={<ListingPage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/bookings" element={<BookingsPage />} />
        <Route path="*" element={<p className="page notice">This page does not exist.</p>} />
      </Routes>
    </>
  )
}
