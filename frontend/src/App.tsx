import { Route, Routes } from 'react-router-dom'

import Header from './components/Header'
import BookingPage from './pages/BookingPage'
import BookingsPage from './pages/BookingsPage'
import HostBookingPage from './pages/HostBookingPage'
import HostingPage from './pages/HostingPage'
import ListingPage from './pages/ListingPage'
import LoginPage from './pages/LoginPage'
import ProfilePage from './pages/ProfilePage'
import SavedPage from './pages/SavedPage'
import SearchPage from './pages/SearchPage'
import SupportPage from './pages/SupportPage'
import TicketPage from './pages/TicketPage'

export default function App() {
  return (
    <>
      <Header />
      <Routes>
        <Route path="/" element={<SearchPage />} />
        <Route path="/listings/:id" element={<ListingPage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/bookings" element={<BookingsPage />} />
        <Route path="/bookings/:id" element={<BookingPage />} />
        <Route path="/saved" element={<SavedPage />} />
        <Route path="/profile" element={<ProfilePage />} />
        <Route path="/hosting" element={<HostingPage />} />
        <Route path="/hosting/:id" element={<HostBookingPage />} />
        <Route path="/support" element={<SupportPage />} />
        <Route path="/support/:id" element={<TicketPage />} />
        <Route path="*" element={<p className="page notice">This page does not exist.</p>} />
      </Routes>
    </>
  )
}
