# website/utils/pagination.py
"""
Pagination utilities for the AIGrader application.
"""

from flask import request, current_app


class Pagination:
    """
    Simple pagination helper class.
    """
    
    def __init__(self, query, page=1, per_page=20, total=None):
        """
        Initialize pagination.
        
        Args:
            query: SQLAlchemy query object
            page: Current page number (1-indexed)
            per_page: Items per page
            total: Optional total count (if not provided, will be calculated)
        """
        self.page = max(1, page)
        self.per_page = min(per_page, current_app.config.get('MAX_ITEMS_PER_PAGE', 100))
        
        if total is not None:
            self.total = total
        else:
            self.total = query.count()
        
        self.items = query.offset((self.page - 1) * self.per_page).limit(self.per_page).all()
    
    @property
    def pages(self):
        """Total number of pages."""
        if self.total == 0:
            return 1
        return (self.total + self.per_page - 1) // self.per_page
    
    @property
    def has_prev(self):
        """Whether there is a previous page."""
        return self.page > 1
    
    @property
    def has_next(self):
        """Whether there is a next page."""
        return self.page < self.pages
    
    @property
    def prev_num(self):
        """Previous page number."""
        return self.page - 1 if self.has_prev else None
    
    @property
    def next_num(self):
        """Next page number."""
        return self.page + 1 if self.has_next else None
    
    @property
    def start_index(self):
        """Starting index for current page (1-indexed for display)."""
        return (self.page - 1) * self.per_page + 1
    
    @property
    def end_index(self):
        """Ending index for current page."""
        return min(self.page * self.per_page, self.total)
    
    def iter_pages(self, left_edge=2, left_current=2, right_current=3, right_edge=2):
        """
        Iterate over page numbers for navigation.
        Yields None for gaps between page ranges.
        """
        last = 0
        for num in range(1, self.pages + 1):
            if num <= left_edge or \
               (num > self.page - left_current - 1 and num < self.page + right_current) or \
               num > self.pages - right_edge:
                if last + 1 != num:
                    yield None
                yield num
                last = num
    
    def to_dict(self):
        """Convert pagination info to dictionary for JSON responses."""
        return {
            'page': self.page,
            'per_page': self.per_page,
            'total': self.total,
            'pages': self.pages,
            'has_prev': self.has_prev,
            'has_next': self.has_next,
            'prev_num': self.prev_num,
            'next_num': self.next_num,
            'start_index': self.start_index,
            'end_index': self.end_index
        }


def get_page_args():
    """
    Get pagination arguments from request.
    
    Returns:
        Tuple of (page, per_page)
    """
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 
                                current_app.config.get('ITEMS_PER_PAGE', 20), 
                                type=int)
    
    # Ensure valid values
    page = max(1, page)
    per_page = min(max(1, per_page), current_app.config.get('MAX_ITEMS_PER_PAGE', 100))
    
    return page, per_page


def paginate(query, page=None, per_page=None):
    """
    Paginate a SQLAlchemy query.
    
    Args:
        query: SQLAlchemy query object
        page: Page number (if None, gets from request)
        per_page: Items per page (if None, gets from request/config)
        
    Returns:
        Pagination object
    """
    if page is None or per_page is None:
        req_page, req_per_page = get_page_args()
        page = page or req_page
        per_page = per_page or req_per_page
    
    return Pagination(query, page, per_page)
