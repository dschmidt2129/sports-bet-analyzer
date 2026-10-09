[app]
title = Sports Bet Analyzer
package.name = sportsbetanalyzer
package.domain = org.sportsbetanalyzer
source.dir = src
source.include_exts = py,png,jpg,kv,atlas,json
version = 0.1.0
requirements = python3,kivy,requests,certifi
orientation = portrait
fullscreen = 0

android.permissions = INTERNET
android.api = 33
android.minapi = 24
android.archs = arm64-v8a,armeabi-v7a

[buildozer]
log_level = 2
warn_on_root = 1
