# renderer options

Historical upstream example: https://github.com/lepture/mistune/blob/6470c42b2087a4649ad0437227cf7b5c570c3a91/README.rst#L87-L90

Setup supplies import mistune and text = "<b>x</b>\nnext" for the upstream placeholder. Retain the reusable callable markdown. It must render HTML, escape raw HTML, and use hard line breaks. Preserve the original XHTML <br /> style and silent expression; checks cover other text and boundary inputs.

```python
renderer = mistune.Renderer(escape=True, hard_wrap=True)
# use this renderer instance
markdown = mistune.Markdown(renderer=renderer)
markdown(text)
```
