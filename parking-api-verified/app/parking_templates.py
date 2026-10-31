"""Technical transaction/identity/idempotency layer; mutations are supplied by Qwen."""
import json
from .parking_generation import uid, q


def runtime(profile,design):
    table_map={e['name']:e for e in profile['entities']}
    fields=table_map['ParkingSession']['fields']
    updates=','.join(q(f['name'])+'=x.'+q(f['name']) for f in fields if f['name']!='id')
    routes=[]
    for op in profile['operations']:
        roles='new[] {'+','.join(json.dumps(r) for r in op['roles'])+'}'
        routes.append('app.MapMethods('+json.dumps(op['path'])+', new[] {'+json.dumps(op['method'])+'}, async (HttpContext c) => {\n'
            'var actor = (Actor)c.Items["Actor"]!;\nif (!'+roles+'.Contains(actor.Role)) throw new ApiError(403,"forbidden","Role not allowed");\n'
            'await Api.Dispatch(c, db, actor, '+json.dumps(op['operation_id'])+');\n});')
    constraints=[]
    for name in ('SessionInput','SessionConfirmation'):
        checks=[]
        for n,s in design['schemas'][name]['properties'].items():
            expr='x.'+n
            if s.get('format')=='uuid':checks.append(expr+' == Guid.Empty')
            if s.get('type')=='string' and s.get('format') is None:
                checks.append('string.IsNullOrWhiteSpace('+expr+')')
                if 'maxLength' in s:checks.append(expr+'.Length > '+str(s['maxLength']))
            if 'minimum' in s:checks.append(expr+' < '+str(s['minimum']))
        constraints.append('public static void Validate('+name+' x) { if ('+' || '.join(checks)+') throw new ApiError(422,"validation","Input constraints violated"); }')
    operations={o['operation_id']:o for o in profile['operations']}
    pages=[{x['name']:x['schema'] for x in o['parameters'] if x['in']=='query'} for o in profile['operations'] if any(x['name']=='page' for x in o['parameters'])]
    pagination=pages[0]
    if any((p['page'],p['pageSize'])!=(pagination['page'],pagination['pageSize']) for p in pages):
        raise ValueError('This profile requires uniform pagination schemas')
    page,size=pagination['page'],pagination['pageSize']
    city=next(x['schema'] for x in operations['listObjects']['parameters'] if x['name']=='city')
    code=HEADER.replace('@@ROUTES@@','\n'.join(routes)).replace('@@DRIVER_A@@',uid('driver-a')).replace('@@DRIVER_B@@',uid('driver-b')).replace('@@ADMIN@@',uid('admin')).replace('@@VALIDATE@@','\n'.join(constraints)).replace('@@UPDATES@@',updates.replace('"','\\"'))
    return code.replace('long page=1,size=50;',f'long page={page["default"]},size={size["default"]};').replace(
        'page<1 || size<1 || size>100',f'page<{page["minimum"]} || size<{size["minimum"]} || size>{size["maximum"]}').replace(
        'city!="spb" && city!="moscow_partner"',' && '.join('city!='+json.dumps(value) for value in city['enum']))


HEADER=r'''using System.Text.Json;
using System.Text.Json.Serialization;
using System.Security.Cryptography;
using System.Text;
using Npgsql;
using NpgsqlTypes;

var builder = WebApplication.CreateBuilder(args);
builder.Logging.ClearProviders();
builder.Logging.AddConsole();
builder.Logging.SetMinimumLevel(LogLevel.Error);
await using var db = NpgsqlDataSource.Create(builder.Configuration.GetConnectionString("Database")
    ?? throw new InvalidOperationException("Database config required"));
var tokens = new Dictionary<string,Guid>();
foreach (var pair in new[] {("Demo:TokenA","@@DRIVER_A@@"),("Demo:TokenB","@@DRIVER_B@@"),("Demo:TokenAdmin","@@ADMIN@@")}) {
    var token = builder.Configuration[pair.Item1];
    if (string.IsNullOrWhiteSpace(token) || token.StartsWith("replace-") || tokens.ContainsKey(token))
        throw new InvalidOperationException("Distinct private demo tokens required");
    tokens.Add(token,Guid.Parse(pair.Item2));
}
var app = builder.Build();
app.Use(async (c,next) => {
    try {
        var auth=c.Request.Headers.Authorization.ToString();
        Guid? account=null;
        if (auth.StartsWith("Bearer ",StringComparison.Ordinal)) {
            var hash=SHA256.HashData(Encoding.UTF8.GetBytes(auth[7..]));
            foreach (var pair in tokens)
                if (CryptographicOperations.FixedTimeEquals(hash,SHA256.HashData(Encoding.UTF8.GetBytes(pair.Key)))) account=pair.Value;
        }
        if (account is null) throw new ApiError(401,"unauthorized","Valid demo token required");
        await using var conn=await db.OpenConnectionAsync(c.RequestAborted);
        await using var cmd=new NpgsqlCommand("SELECT role FROM \"Account\" WHERE id=@id",conn);
        cmd.Parameters.AddWithValue("id",account.Value);
        var role=await cmd.ExecuteScalarAsync(c.RequestAborted) as string;
        if (role is null) throw new ApiError(401,"unauthorized","Account unavailable");
        c.Items["Actor"]=new Actor(account.Value,role);
        await next(c);
    } catch (ApiError e) {await Api.Error(c,e.Status,e.Code,e.Message);}
      catch (JsonException) {await Api.Error(c,400,"invalid_json","Invalid request body");}
      catch (BadHttpRequestException) {await Api.Error(c,400,"invalid_request","Invalid request");}
      catch (PostgresException e) when (e.SqlState=="23505") {await Api.Error(c,409,"conflict","Active session or idempotency conflict");}
      catch (PostgresException e) when (e.SqlState=="23503") {await Api.Error(c,404,"not_found","Referenced object missing");}
      catch (PostgresException e) when (e.SqlState is "23514" or "23502" or "22001") {await Api.Error(c,422,"validation","Database constraint rejected input");}
      catch (Exception) {await Api.Error(c,503,"unavailable","Operation unavailable");}
});
@@ROUTES@@
await app.RunAsync();

public sealed record Actor(Guid Id,string Role);
public sealed class ApiError(int status,string code,string message):Exception(message) {
    public int Status {get;}=status; public string Code {get;}=code;
}
public static class Api {
    public static readonly JsonSerializerOptions Json=new(JsonSerializerDefaults.Web) {UnmappedMemberHandling=JsonUnmappedMemberHandling.Disallow};
    public static Task Error(HttpContext c,int status,string code,string message) {
        c.Response.StatusCode=status;
        return c.Response.WriteAsJsonAsync(new {code,message,traceId=c.TraceIdentifier});
    }
    public static Guid Id(string? value) => Guid.TryParse(value,out var id) && id!=Guid.Empty ? id : throw new ApiError(400,"invalid_uuid","UUID required");
    @@VALIDATE@@
    public static async Task Dispatch(HttpContext c,NpgsqlDataSource db,Actor actor,string op) {
        if (op=="createSession") {
            var input=await JsonSerializer.DeserializeAsync<SessionInput>(c.Request.Body,Json,c.RequestAborted) ?? throw new ApiError(400,"body_required","Body required");
            Validate(input);var id=Id(c.Request.RouteValues["vehicleId"]?.ToString());
            await Mutate(c,db,actor,op,id,input.idempotencyKey,input,201,tx=>ParkingHandlers.createSession(tx,id,input));return;
        }
        if (op=="confirmSession") {
            var input=await JsonSerializer.DeserializeAsync<SessionConfirmation>(c.Request.Body,Json,c.RequestAborted) ?? throw new ApiError(400,"body_required","Body required");
            Validate(input);var id=Id(c.Request.RouteValues["sessionId"]?.ToString());
            await Mutate(c,db,actor,op,id,input.idempotencyKey,input,200,tx=>ParkingHandlers.confirmSession(tx,id,input));return;
        }
        await using var conn=await db.OpenConnectionAsync(c.RequestAborted);
        await using var tx=await conn.BeginTransactionAsync(c.RequestAborted);
        var context=new SessionContext(conn,tx,actor,c.RequestAborted,DateTimeOffset.UtcNow);
        string table,where="TRUE";object? value=null;
        if (op=="listVehicles") {table="Vehicle";if(actor.Role=="driver"){where="\"driverId\"=@value";value=actor.Id;}}
        else if (op=="listObjects") {
            table="ParkingObject";var city=c.Request.Query["city"].ToString();
            if(city!="spb" && city!="moscow_partner")throw new ApiError(400,"invalid_city","Source city required");
            where="city=@value";value=city;
        } else if(op=="listVehicleSessions") {
            table="ParkingSession";var id=Id(c.Request.RouteValues["vehicleId"]?.ToString());
            await context.RequireVehicle(id);where="\"vehicleId\"=@value";value=id;
        } else {table="ParkingSession";if(c.Request.Query.ContainsKey("vehicleId")){where="\"vehicleId\"=@value";value=Id(c.Request.Query["vehicleId"]);}}
        long page=1,size=50;
        if(c.Request.Query.ContainsKey("page") && !long.TryParse(c.Request.Query["page"],out page))throw new ApiError(400,"pagination","Invalid page");
        if(c.Request.Query.ContainsKey("pageSize") && !long.TryParse(c.Request.Query["pageSize"],out size))throw new ApiError(400,"pagination","Invalid pageSize");
        if(page<1 || size<1 || size>100 || page>long.MaxValue/size)throw new ApiError(400,"pagination","Pagination out of range");
        await using var count=context.Command("SELECT count(*) FROM \""+table+"\" WHERE "+where);
        if(value is not null)count.Parameters.AddWithValue("value",value);
        var total=(long)(await count.ExecuteScalarAsync(c.RequestAborted))!;
        await using var cmd=context.Command("SELECT to_jsonb(t)::text FROM \""+table+"\" t WHERE "+where+" ORDER BY id LIMIT @size OFFSET @offset");
        if(value is not null)cmd.Parameters.AddWithValue("value",value);
        cmd.Parameters.AddWithValue("size",size);cmd.Parameters.AddWithValue("offset",(page-1)*size);
        var items=new List<JsonElement>();
        await using(var reader=await cmd.ExecuteReaderAsync(c.RequestAborted))
            while(await reader.ReadAsync(c.RequestAborted))items.Add(JsonSerializer.Deserialize<JsonElement>(reader.GetString(0)));
        await tx.CommitAsync(c.RequestAborted);
        await c.Response.WriteAsJsonAsync(new {items,page,pageSize=size,total});
    }
    public static async Task Mutate<T>(HttpContext c,NpgsqlDataSource db,Actor actor,string op,Guid target,string key,T input,int status,Func<SessionContext,Task<ParkingSession>> action) {
        await using var conn=await db.OpenConnectionAsync(c.RequestAborted);
        await using var transaction=await conn.BeginTransactionAsync(c.RequestAborted);
        await using(var lockCmd=new NpgsqlCommand("SELECT pg_advisory_xact_lock(hashtextextended(@scope,0))",conn,transaction)) {
            lockCmd.Parameters.AddWithValue("scope",actor.Id+":"+key);await lockCmd.ExecuteNonQueryAsync(c.RequestAborted);
        }
        var fingerprint=Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(op+":"+target+":"+JsonSerializer.Serialize(input,Json))));
        await using(var replay=new NpgsqlCommand("SELECT fingerprint,response::text,status FROM \"RequestReplay\" WHERE \"actorId\"=@actor AND key=@key",conn,transaction)) {
            replay.Parameters.AddWithValue("actor",actor.Id);replay.Parameters.AddWithValue("key",key);
            await using var reader=await replay.ExecuteReaderAsync(c.RequestAborted);
            if(await reader.ReadAsync(c.RequestAborted)) {
                if(reader.GetString(0)!=fingerprint)throw new ApiError(409,"idempotency_conflict","Key already used for other data");
                var json=reader.GetString(1);var savedStatus=reader.GetInt32(2);await reader.DisposeAsync();
                await transaction.CommitAsync(c.RequestAborted);c.Response.StatusCode=savedStatus;c.Response.ContentType="application/json";
                await c.Response.WriteAsync(json);return;
            }
        }
        DateTimeOffset now;
        await using(var clock=new NpgsqlCommand("SELECT transaction_timestamp()",conn,transaction))now=new DateTimeOffset((DateTime)(await clock.ExecuteScalarAsync(c.RequestAborted))!);
        var context=new SessionContext(conn,transaction,actor,c.RequestAborted,now);
        var result=await action(context);var response=JsonSerializer.Serialize(result,Json);
        await using(var save=new NpgsqlCommand("INSERT INTO \"RequestReplay\" (\"actorId\",key,fingerprint,response,status) VALUES (@actor,@key,@fingerprint,@response,@status)",conn,transaction)) {
            save.Parameters.AddWithValue("actor",actor.Id);save.Parameters.AddWithValue("key",key);save.Parameters.AddWithValue("fingerprint",fingerprint);
            save.Parameters.AddWithValue("response",NpgsqlDbType.Jsonb,response);save.Parameters.AddWithValue("status",status);
            await save.ExecuteNonQueryAsync(c.RequestAborted);
        }
        await transaction.CommitAsync(c.RequestAborted);c.Response.StatusCode=status;c.Response.ContentType="application/json";await c.Response.WriteAsync(response);
    }
}
public sealed class SessionContext(NpgsqlConnection conn,NpgsqlTransaction transaction,Actor actor,CancellationToken ct,DateTimeOffset now) {
    public DateTimeOffset Now {get;}=now;
    public NpgsqlCommand Command(string sql)=>new(sql,conn,transaction);
    public async Task RequireVehicle(Guid id) {
        await using var cmd=Command("SELECT \"driverId\" FROM \"Vehicle\" WHERE id=@id FOR UPDATE");cmd.Parameters.AddWithValue("id",id);
        var owner=await cmd.ExecuteScalarAsync(ct);
        if(owner is null)throw new ApiError(404,"vehicle_not_found","Vehicle not found");
        if(actor.Role!="admin" && (Guid)owner!=actor.Id)throw new ApiError(403,"forbidden","Vehicle belongs to another driver");
    }
    public async Task RequireObject(Guid id) {
        await using var cmd=Command("SELECT \"geometryState\" FROM \"ParkingObject\" WHERE id=@id");cmd.Parameters.AddWithValue("id",id);
        var state=await cmd.ExecuteScalarAsync(ct);
        if(state is null)throw new ApiError(404,"object_not_found","Object not found");
        if((string)state!="valid")throw new ApiError(422,"invalid_object","Object quarantined");
    }
    public async Task<ParkingSession> LoadSession(Guid id) {
        ParkingSession session;
        await using(var cmd=Command("SELECT to_jsonb(s)::text FROM \"ParkingSession\" s WHERE id=@id FOR UPDATE")) {
            cmd.Parameters.AddWithValue("id",id);var value=await cmd.ExecuteScalarAsync(ct) as string;
            if(value is null)throw new ApiError(404,"session_not_found","Session not found");
            session=JsonSerializer.Deserialize<ParkingSession>(value,Api.Json)!;
        }
        await RequireVehicle(session.vehicleId);return session;
    }
    public Task<ParkingSession> InsertSession(ParkingSession row)=>Write(row,true);
    public Task<ParkingSession> SaveSession(ParkingSession row)=>Write(row,false);
    private async Task<ParkingSession> Write(ParkingSession row,bool insert) {
        var sql=insert ? "INSERT INTO \"ParkingSession\" SELECT (jsonb_populate_record(NULL::\"ParkingSession\",@data)).* RETURNING to_jsonb(\"ParkingSession\")::text"
            : "UPDATE \"ParkingSession\" SET @@UPDATES@@ FROM jsonb_populate_record(NULL::\"ParkingSession\",@data) x WHERE \"ParkingSession\".id=x.id RETURNING to_jsonb(\"ParkingSession\")::text";
        await using var cmd=Command(sql);cmd.Parameters.AddWithValue("data",NpgsqlDbType.Jsonb,JsonSerializer.Serialize(row,Api.Json));
        var result=await cmd.ExecuteScalarAsync(ct) as string;
        if(result is null)throw new ApiError(409,"write_conflict","Session write conflict");
        return JsonSerializer.Deserialize<ParkingSession>(result,Api.Json)!;
    }
}
'''
