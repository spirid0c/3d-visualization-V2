import urllib.request
import ssl
import os

def download_file(url, filename):
    print(f"Downloading {filename} from {url}...")
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        with urllib.request.urlopen(url, context=ctx) as response, open(filename, 'wb') as out_file:
            data = response.read()
            out_file.write(data)
        print(f"Successfully downloaded {filename}")
    except Exception as e:
        print(f"Failed to download {filename}: {e}")

if __name__ == "__main__":
    base_url = "https://ftp.cpc.ncep.noaa.gov/wd51we/wgrib/machines/Windows10/"
    download_file(base_url + "wgrib.exe", "wgrib.exe")
    download_file(base_url + "cygwin1.dll", "cygwin1.dll")
    print("\nwgrib setup complete. Executables are in the current directory.")
