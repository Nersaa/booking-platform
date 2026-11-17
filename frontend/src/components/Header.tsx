import { Link, NavLink } from 'react-router-dom'

import { useAuth } from '../auth'

export default function Header() {
  const { user, isLoggedIn } = useAuth()

  return (
    <header className="header">
      <Link to="/" className="brand">
        Booking Platform
      </Link>
      <nav className="nav">
        <NavLink to="/" end>
          Search
        </NavLink>
        {isLoggedIn ? (
          <>
            <NavLink to="/saved">Saved</NavLink>
            <NavLink to="/bookings">My bookings</NavLink>
            {user?.is_host && <NavLink to="/hosting">Hosting</NavLink>}
            <NavLink to="/support">Help</NavLink>
            <NavLink to="/profile" className="nav-profile">
              {user?.first_name ?? 'Profile'}
            </NavLink>
          </>
        ) : (
          <NavLink to="/login">Log in</NavLink>
        )}
      </nav>
    </header>
  )
}
