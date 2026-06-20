@echo off
rem AIT project-local wrapper -- pinned to this repository for dogfood development.
"%~dp0..\..\.venv\Scripts\python.exe" -m ait.cli %*
