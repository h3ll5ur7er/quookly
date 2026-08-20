import { Component, inject, signal } from '@angular/core';
import { map } from 'rxjs';
import { AsyncPipe } from '@angular/common';
import { StatusService } from '@api';

@Component({
  selector: 'app-status',
  imports: [AsyncPipe],
  templateUrl: './status.component.html',
  styleUrls: ['./status.component.scss']
})
export class StatusComponent {
  protected readonly title = signal('MyFullstackTemplate Status');
  protected readonly status = inject(StatusService).getStatus().pipe(map(status => status.status));
}
