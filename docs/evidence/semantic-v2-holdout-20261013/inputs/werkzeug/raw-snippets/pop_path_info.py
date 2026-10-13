    """Removes and returns the next segment of `PATH_INFO`, pushing it onto
    `SCRIPT_NAME`.  Returns `None` if there is nothing left on `PATH_INFO`.

    If the `charset` is set to `None` bytes are returned.

    If there are empty segments (``'/foo//bar``) these are ignored but
    properly pushed to the `SCRIPT_NAME`:

    >>> env = {'SCRIPT_NAME': '/foo', 'PATH_INFO': '/a/b'}
    >>> pop_path_info(env)
    'a'
    >>> env['SCRIPT_NAME']
    '/foo/a'
    >>> pop_path_info(env)
    'b'
    >>> env['SCRIPT_NAME']
    '/foo/a/b'

    .. deprecated:: 2.2
        Will be removed in Werkzeug 2.3.

    .. versionadded:: 0.5

    .. versionchanged:: 0.9
       The path is now decoded and a charset and encoding
       parameter can be provided.

    :param environ: the WSGI environment that is modified.
    :param charset: The ``encoding`` parameter passed to
        :func:`bytes.decode`.
    :param errors: The ``errors`` paramater passed to
        :func:`bytes.decode`.
    """
