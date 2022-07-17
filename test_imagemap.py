from imagemap import ImageMap

def test_imagemap():
  imagemap = ImageMap({
    "images": {
      "example": [
        "/a.jpg",
        "/b.png",
        "/a.gif",
        "/b.gifv",
      ],
      "hidden": [
        "/a.jpg",
      ]
    },
    "aliases": {
      "example": ["alias", "other_alias"]
    },
    "hidden": ["hidden"]
  }, {
    "extensions": ["jpg", "jpeg", "png", "bmp", "tif", "gif", "gifv","avi"],
    "animated_extensions": ["gif","avi","gifv"],
    "switchable_extensions": ["jpeg","jpg","gif","png"],
  })

  assert imagemap.get("example") == (["/a.jpg", "/b.png", "/a.gif", "/b.gifv"], "example")
  assert imagemap.get("alias") == (["/a.jpg", "/b.png", "/a.gif", "/b.gifv"], "example")
  assert imagemap.get("other_alias") == (["/a.jpg", "/b.png", "/a.gif", "/b.gifv"], "example")
  assert imagemap.get("exmple") == (["/a.jpg", "/b.png", "/a.gif", "/b.gifv"], "example")

  assert imagemap.get("example", "jpg") == (["/a.jpg"], "example")
  assert imagemap.get("example", "jpeg") == (["/a.jpeg", "/b.jpeg"], "example")
  assert imagemap.get("example", "avi") == (["/a.gif", "/b.gifv"], "example")
