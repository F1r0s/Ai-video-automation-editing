import urllib.request, zipfile, io, os
os.makedirs('assets', exist_ok=True)
urls = ['https://fonts.google.com/download?family=Roboto', 'https://fonts.google.com/download?family=Oswald', 'https://fonts.google.com/download?family=Bebas+Neue', 'https://fonts.google.com/download?family=Anton']
for url in urls:
    try:
        r = urllib.request.urlopen(url)
        with zipfile.ZipFile(io.BytesIO(r.read())) as z:
            for f in z.namelist():
                if f.endswith('.ttf') and not '/' in f:
                    z.extract(f, 'assets/')
    except Exception as e: print(url, e)
