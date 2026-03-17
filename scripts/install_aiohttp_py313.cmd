@echo off
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvarsall.bat" arm64
set DISTUTILS_USE_SDK=1
set MSSdk=1
set CC=cl.exe
where cl
"C:\Users\abdurrahmankuli\AppData\Local\Programs\Python\Python313-arm64\python.exe" -m pip install aiohttp==3.13.3