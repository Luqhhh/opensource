    renderer = mistune.Renderer(escape=True, hard_wrap=True)
    # use this renderer instance
    markdown = mistune.Markdown(renderer=renderer)
    markdown(text)
