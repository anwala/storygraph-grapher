# [storygraph-grapher](http://storygraph.cs.odu.edu/)
Git repo for storygraph graph generator

## To build/run images/containers
Replace ```[/host/path/to/data/]``` in docker-compose.yml with host location of data folder. Sample content of ```[/host/path/to/data/]``` can be found [here](https://github.com/anwala/storygraph-data)

```
.../storygraph-grapher$ docker-compose up -d --build
```

## To shutdown container
```
.../storygraph-grapher$ docker-compose down
```
