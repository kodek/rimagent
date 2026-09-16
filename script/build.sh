#!/bin/zsh
# Build RimBridge in place; output lands in mod/1.6/Assemblies (symlinked into the RimWorld Mods folder).
set -e
cd "$(dirname "$0")/../mod"
dotnet build Source/RimBridge.csproj -c Release --nologo -v quiet "$@"
ls -la 1.6/Assemblies/RimBridge.dll
