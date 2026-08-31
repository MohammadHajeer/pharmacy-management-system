from django.core.paginator import Paginator


DEFAULT_PAGE_SIZE = 25


def pagination_context(request, queryset, *, context_name):
    """Paginate an already filtered, deterministically ordered registry queryset."""
    page_obj = Paginator(queryset, DEFAULT_PAGE_SIZE).get_page(request.GET.get("page"))
    return {
        context_name: page_obj.object_list,
        "page_obj": page_obj,
        "page_numbers": page_obj.paginator.get_elided_page_range(
            page_obj.number, on_each_side=2, on_ends=1,
        ),
    }
