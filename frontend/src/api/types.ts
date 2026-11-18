// Shapes of the API responses the pages use. Money is in minor units (cents).

export type Page<T> = { items: T[]; total: number; limit: number; offset: number }

export type SearchItem = {
  id: string
  title: string
  property_type: string
  country: string
  city: string
  latitude: string
  longitude: string
  max_guests: number
  bedrooms: number
  beds: number
  bathrooms: number
  amenities: string[]
  cover_photo_url: string | null
  rating: string | null
  review_count: number
  currency: string
  nightly_price: number
  distance_km: number | null
  stay_total: number | null
}

export type Listing = {
  id: string
  host: { id: string; first_name: string }
  title: string
  description: string
  property_type: string
  country: string
  city: string
  max_guests: number
  bedrooms: number
  beds: number
  bathrooms: number
  amenities: { code: string; name: string }[]
  photos: { id: string; large_url: string | null; thumb_url: string | null }[]
  rating: string | null
  review_count: number
}

export type Review = {
  id: string
  rating: number
  text: string
  author: { id: string; first_name: string }
  host_reply: string
  created_at: string
}

export type ReviewPage = { count: number; results: Review[] }

export type Calendar = {
  currency: string
  min_nights: number
  max_nights: number
  days: { date: string; available: boolean; nightly_price: number }[]
}

export type Quote = {
  currency: string
  nights: { date: string; price: number }[]
  subtotal: number
  discount: number
  cleaning_fee: number
  total: number
}

export type BookingStatus = 'pending_payment' | 'confirmed' | 'cancelled' | 'expired' | 'completed'

export type Booking = {
  id: string
  listing_id: string
  status: BookingStatus
  check_in: string
  check_out: string
  guests: number
  currency: string
  subtotal: number
  discount: number
  cleaning_fee: number
  total: number
  refund_amount: number
  cancelled_by: 'guest' | 'host' | null
  hold_expires_at: string | null
  created_at: string
}

export type Payment = { id: string; checkout_url: string }

export type User = {
  id: string
  email: string
  first_name: string
  last_name: string
  is_host: boolean
}

export type TicketStatus = 'open' | 'answered' | 'closed'

export type Ticket = {
  id: string
  topic: string
  subject: string
  booking_id: string | null
  status: TicketStatus
  created_at: string
  updated_at: string
}

export type SupportMessage = {
  id: string
  text: string
  from_support: boolean
  author_name: string
  created_at: string
}

export type TicketDetail = Ticket & { messages: SupportMessage[] }

// Django REST framework's page format (Catalog), unlike Booking's `Page`.
export type DrfPage<T> = { count: number; results: T[] }

export type Amenity = { code: string; name: string }

export type SavedListing = {
  id: string
  title: string
  city: string
  country: string
  property_type: string
  rating: string | null
  review_count: number
  cover_url: string | null
  saved_at: string
}

export type BookingMessage = { id: string; text: string; from_host: boolean; created_at: string }

export type PendingReview = { booking_id: string; review_deadline: string }

export type ListingStatus = 'draft' | 'pending_review' | 'published' | 'rejected' | 'archived'

export type HostPhoto = {
  id: string
  status: 'pending_upload' | 'processing' | 'ready' | 'failed'
  thumb_url: string | null
}

export type HostListing = {
  id: string
  status: ListingStatus
  rejection_reason: string
  title: string
  description: string
  property_type: string
  country: string
  city: string
  address: string
  latitude: string
  longitude: string
  max_guests: number
  bedrooms: number
  beds: number
  bathrooms: number
  amenities: Amenity[]
  photos: HostPhoto[]
}

export type PhotoUpload = {
  photo: HostPhoto
  upload: { url: string; fields: Record<string, string> }
}

export type Pricing = {
  currency: string
  nightly_price: number
  weekend_price: number | null
  cleaning_fee: number
  min_nights: number
  max_nights: number
  weekly_discount_percent: number
  monthly_discount_percent: number
}

export type Block = { id: string; start_date: string; end_date: string; note: string }

export type HostListingPage = { count: number; results: HostListing[] }
