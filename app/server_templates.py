"""Technical scaffold only. Domain.cs and SQL must come from the model."""

PROJECT = '''<Project Sdk="Microsoft.NET.Sdk.Web">
  <PropertyGroup>
    <TargetFramework>net10.0</TargetFramework>
    <LangVersion>14.0</LangVersion>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
    <TreatWarningsAsErrors>true</TreatWarningsAsErrors>
  </PropertyGroup>
  <ItemGroup><PackageReference Include="Npgsql" Version="10.0.3" /></ItemGroup>
</Project>
'''

PROGRAM = '''using Npgsql;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json.Serialization;

var builder = WebApplication.CreateBuilder(args);
builder.Logging.ClearProviders();
builder.Logging.AddConsole();
builder.Logging.SetMinimumLevel(LogLevel.Error);
builder.Services.ConfigureHttpJsonOptions(o =>
    o.SerializerOptions.UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow);
builder.Services.Configure<RouteHandlerOptions>(o => o.ThrowOnBadRequest = true);
var connection = builder.Configuration.GetConnectionString("Database")
    ?? throw new InvalidOperationException("Database configuration missing");
await using var dataSource = NpgsqlDataSource.Create(connection);
var identity = new DemoIdentity(builder.Configuration);
var app = builder.Build();
app.Use(async (context, next) => {
    var employee = identity.Resolve(context.Request.Headers.Authorization.ToString());
    if (employee is null) {
        context.Response.StatusCode = 401;
        await context.Response.WriteAsJsonAsync(new { code = "unauthorized", message = "Valid demo bearer required" });
        return;
    }
    context.Items["VerifiedEmployee"] = employee;
    try { await next(context); }
    catch (BadHttpRequestException) when (!context.Response.HasStarted) {
        context.Response.StatusCode = 400;
        await context.Response.WriteAsJsonAsync(new { code = "invalid_request", message = "Invalid request body" });
    }
    catch (Exception) when (!context.Response.HasStarted) {
        context.Response.StatusCode = 500;
        await context.Response.WriteAsJsonAsync(new { code = "server_error", message = "Server operation failed" });
    }
});
DomainEndpoints.Map(app, dataSource);
await app.RunAsync();

public sealed class DemoIdentity {
    private readonly (byte[] Token, string Employee)[] users;
    public DemoIdentity(IConfiguration config) {
        string Required(string name) {
            var value = config[name];
            if (string.IsNullOrWhiteSpace(value) || value.StartsWith("replace-"))
                throw new InvalidOperationException("Demo identity configuration missing");
            return value;
        }
        var a = Required("Demo:TokenA"); var b = Required("Demo:TokenB");
        var employeeA = Required("Demo:EmployeeA"); var employeeB = Required("Demo:EmployeeB");
        if (a == b || employeeA == employeeB) throw new InvalidOperationException("Demo identities must differ");
        users = [(SHA256.HashData(Encoding.UTF8.GetBytes(a)), employeeA),
                 (SHA256.HashData(Encoding.UTF8.GetBytes(b)), employeeB)];
    }
    public string? Resolve(string authorization) {
        if (!authorization.StartsWith("Bearer ", StringComparison.Ordinal)) return null;
        var hash = SHA256.HashData(Encoding.UTF8.GetBytes(authorization[7..]));
        foreach (var user in users)
            if (CryptographicOperations.FixedTimeEquals(hash, user.Token)) return user.Employee;
        return null;
    }
    public static string Employee(HttpContext context) =>
        context.Items["VerifiedEmployee"] as string ?? throw new InvalidOperationException("Unverified identity");
}
'''

DOCKERFILE = '''FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
WORKDIR /source
COPY src/Api.csproj ./
RUN dotnet restore Api.csproj
COPY src/ ./
RUN dotnet publish Api.csproj -c Release -o /out --no-restore
FROM mcr.microsoft.com/dotnet/aspnet:10.0
WORKDIR /app
COPY --from=build /out ./
USER app
ENV ASPNETCORE_URLS=http://+:8080
ENTRYPOINT ["dotnet", "Api.dll"]
'''

COMPOSE = '''services:
  db:
    image: postgres:17.9
    environment:
      POSTGRES_USER: app
      POSTGRES_DB: app
      POSTGRES_PASSWORD: ${DB_PASSWORD:?Set DB_PASSWORD}
    volumes:
      - data:/var/lib/postgresql/data
      - ./db:/docker-entrypoint-initdb.d:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -h 127.0.0.1 -U app -d app"]
      interval: 2s
      timeout: 3s
      retries: 30
    networks: [private]
  api:
    build: .
    depends_on:
      db:
        condition: service_healthy
    environment:
      ConnectionStrings__Database: Host=db;Database=app;Username=app;Password=${DB_PASSWORD:?Set DB_PASSWORD}
      Demo__TokenA: ${DEMO_TOKEN_A:?Set DEMO_TOKEN_A}
      Demo__TokenB: ${DEMO_TOKEN_B:?Set DEMO_TOKEN_B}
      Demo__EmployeeA: ${DEMO_EMPLOYEE_A:?Set DEMO_EMPLOYEE_A}
      Demo__EmployeeB: ${DEMO_EMPLOYEE_B:?Set DEMO_EMPLOYEE_B}
    ports: ["127.0.0.1:${API_PORT:-18880}:8080"]
    read_only: true
    tmpfs: [/tmp]
    cap_drop: [ALL]
    security_opt: ["no-new-privileges:true"]
    pids_limit: 128
    mem_limit: 512m
    cpus: 1
    networks: [private]
volumes:
  data:
networks:
  private:
    internal: true
'''

ENV_EXAMPLE = '''# Local demo only. Replace all three secret placeholders; never commit .env.
DB_PASSWORD=replace-with-random-database-password
DEMO_TOKEN_A=replace-with-random-demo-token-a
DEMO_TOKEN_B=replace-with-random-demo-token-b
DEMO_EMPLOYEE_A=11111111-1111-4111-8111-111111111111
DEMO_EMPLOYEE_B=22222222-2222-4222-8222-222222222222
API_PORT=18880
'''


def scaffold():
    return {'src/Api.csproj': PROJECT, 'src/Program.cs': PROGRAM, 'Dockerfile': DOCKERFILE,
            'compose.yaml': COMPOSE, '.env.example': ENV_EXAMPLE,
            '.gitignore': '.env\n.env.*\n!.env.example\nbin/\nobj/\n',
            '.dockerignore': '.env\n.env.*\n**/bin\n**/obj\n.git\n',
            'README.md': '''# Generated server prototype

ASP.NET Core / .NET 10 / C# 14; PostgreSQL 17.9. Domain code and versioned
db/001_init.sql are model-generated from the supplied contract. See provenance.json.
This is demo bearer identification, not corporate registration or authentication.
The server validates configured tokens and derives the owner from its verified context.

Copy .env.example to local .env, set three random secrets and a free loopback API_PORT.
Run `docker compose --env-file .env up --build -d`. SQL initialization runs once
on a new database volume. To restart only the server: `docker compose restart api`.
`docker compose down` retains the database volume. Do not remove it to test persistence.
Use Authorization: Bearer <your local demo token>; never put the token in source or reports.
API paths, schemas and constraints: contract/openapi.json and contract/design.json.
The database has no published host port. The API binds only to loopback.
No Angular/PWA, industrial identity, CI/CD or application deployment is included.
Python pipeline credentials are not needed by this application.
'''}
