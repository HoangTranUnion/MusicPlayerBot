def alter_title(title):
    """
    Alters the title of the song to be usable for Windows.
    Support for other operating system will be added later.
    :param title: The title of the song.
    :return: A modified version of the title.
    """
    illegal = ["\\", "<", ">", "/", "|", "?", "*"]
    for restriction in illegal:
        title = title.replace(restriction, "_")
    title = title.replace("\"", "\'")
    title = title.replace(":", " -")
    return title
