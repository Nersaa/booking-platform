from rest_framework.pagination import CursorPagination


class CreatedAtCursorPagination(CursorPagination):
    ordering = ("-created_at", "-id")
    page_size = 20
    max_page_size = 100
    page_size_query_param = "page_size"
