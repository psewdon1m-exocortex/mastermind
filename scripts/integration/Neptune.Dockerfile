FROM mcr.microsoft.com/dotnet/sdk:10.0.400@sha256:4beef5b8919dcaa2dc924233bd069257e883cc7a061e09088a97d152d6a48510 AS build
WORKDIR /src
COPY . .
RUN dotnet publish src/Neptune.Linux/Neptune.Linux.csproj --configuration Release --output /release
FROM mcr.microsoft.com/dotnet/aspnet:10.0.11@sha256:011bb5f30180717b1c8b65822ff2c99bcb96bc65af0164589751b83c7b4949f7
WORKDIR /app
COPY --from=build /release /app
ENTRYPOINT ["/bin/sh", "/fixture/neptune-entry.sh"]
