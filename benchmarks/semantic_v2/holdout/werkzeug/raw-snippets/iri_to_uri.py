    """Convert an IRI to a URI. All non-ASCII and unsafe characters are
    quoted. If the URL has a domain, it is encoded to Punycode.

    >>> iri_to_uri('http://\\u2603.net/p\\xe5th?q=\\xe8ry%DF')
    'http://xn--n3h.net/p%C3%A5th?q=%C3%A8ry%DF'

    :param iri: The IRI to convert.
    :param charset: The encoding of the IRI.
    :param errors: Error handler to use during ``bytes.encode``.
    :param safe_conversion: Return the URL unchanged if it only contains
        ASCII characters and no whitespace. See the explanation below.

    There is a general problem with IRI conversion with some protocols
    that are in violation of the URI specification. Consider the
    following two IRIs::

        magnet:?xt=uri:whatever
        itms-services://?action=download-manifest

    After parsing, we don't know if the scheme requires the ``//``,
    which is dropped if empty, but conveys different meanings in the
    final URL if it's present or not. In this case, you can use
    ``safe_conversion``, which will return the URL unchanged if it only
    contains ASCII characters and no whitespace. This can result in a
    URI with unquoted characters if it was not already quoted correctly,
    but preserves the URL's semantics. Werkzeug uses this for the
    ``Location`` header for redirects.

    .. versionchanged:: 0.15
        All reserved characters remain unquoted. Previously, only some
        reserved characters were left unquoted.

    .. versionchanged:: 0.9.6
       The ``safe_conversion`` parameter was added.

    .. versionadded:: 0.6
    """
