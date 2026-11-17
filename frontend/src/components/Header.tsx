import { Link, NavLink } from 'react-router-dom'

import { useAuth } from '../auth'

export default function Header() {
  const { user, isLoggedIn, logout } = useAuth()

  return (
    <header className="header">
      <Link to="/" className="brand">
        Booking Platform
      </Link>
      <nav className="nav">
        <NavLink to="/">Search</NavLink>
        {isLoggedIn && <NavLink to="/bookings">My bookings</NavLink>}
        {isLoggedIn && <NavLink to="/support">Help</NavLink>}
        {isLoggedIn ? (
          <button className="link-button" onClick={logout}>
            Log out{user ? ` (${user.first_name})` : ''}
          </button>
        ) : (
          <NavLink to="/login">Log in</NavLink>
        )}
      </nav>
    </header>
  )
}
